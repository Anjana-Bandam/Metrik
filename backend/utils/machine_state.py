"""
machine_state.py
----------------
Fleet state: machine run-states, live telemetry simulation, and the
human-in-the-loop event log (tool changes, acknowledgements, feedback).

Machines are NOT all running all the time. A real shop has machines idle
between jobs, machines down for a tool change, and machines powered off.
Only RUNNING machines accumulate tool runtime and stream telemetry.

Metrik never starts or stops a machine. State changes here mirror what
the machine reports; the tool-change / acknowledge actions are recorded
because a *person* did them on the floor.
"""

import json
import random
import uuid
from dataclasses import dataclass, field, asdict, fields
from datetime import datetime, timezone
from typing import List, Dict, Optional

from utils.wear_features import (
    BASELINE_WINDOWS, raw_stat_columns, force_energy, ewm_update,
)

RUNNING = "RUNNING"
IDLE = "IDLE"
TOOL_CHANGE = "TOOL_CHANGE"
OFFLINE = "OFFLINE"

# ---------------------------------------------------------------------------
# Condition-monitoring signals for the demo fleet
#
# The demo machines have no physical dynamometer or accelerometer. Rather than
# synthesise plausible-looking force and vibration traces - which never quite
# match the real distribution, and quietly push the wear model outside the
# range it was fitted on - Metrik REPLAYS the measured window statistics of the
# three real PHM 2010 cutters the model was trained on.
#
# So a demo machine's wear curve is a real worn tool's wear curve, sampled from
# real cutting signals. What is simulated is which tool is in which spindle and
# how fast it is being consumed, not the physics.
#
# A production install never touches this: it feeds live sensor samples into
# wear_features.window_stats() and the rest of the chain is identical.
# ---------------------------------------------------------------------------
_REPLAY = None            # lazily loaded npz bundle written by train_wear_model.py
_REPLAY_CUTTERS: List[str] = []


def _load_replay():
    """Load the replay bundle once, tolerating its absence."""
    global _REPLAY, _REPLAY_CUTTERS
    if _REPLAY is not None:
        return _REPLAY
    import os
    import numpy as np
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "models", "metrik_wear_replay.npz")
    try:
        _REPLAY = np.load(path, allow_pickle=False)
        _REPLAY_CUTTERS = [str(c) for c in _REPLAY["cutters"]]
    except (FileNotFoundError, OSError):
        _REPLAY = {}
        _REPLAY_CUTTERS = []
    return _REPLAY


NOMINAL_TOOL_LIFE_MIN = 250.0   # app-side tool life, in minutes of runtime
PHM_TOOL_LIFE_S = 1380.0        # cutting seconds spanned by a real PHM cutter

STATE_LABELS = {
    RUNNING: "Running",
    IDLE: "Idle - no job loaded",
    TOOL_CHANGE: "Tool change in progress",
    OFFLINE: "Offline - not connected",
}


@dataclass
class ToolChangeEvent:
    """A tool change logged by a human. This is our ground-truth label."""
    event_id: str
    machine_id: str
    logged_by: str
    logged_at: str
    runtime_at_change: float
    predicted_risk_at_change: float
    was_actually_worn: Optional[bool] = None   # operator's verdict
    note: str = ""


@dataclass
class AlertAck:
    """An operator acknowledging or dismissing a wear alert, with a reason."""
    ack_id: str
    machine_id: str
    acked_by: str
    acked_at: str
    risk_at_ack: float
    decision: str      # 'accepted' | 'dismissed' | 'snoozed'
    reason: str = ""


@dataclass
class Machine:
    machine_id: str
    name: str
    owner: str
    material_type: str = "M"
    tool_material: str = "carbide"
    state: str = RUNNING
    location: str = "Bay 1"

    # Live telemetry
    spindle_speed: float = 1500.0
    spindle_torque: float = 40.0
    tool_runtime: float = 0.0
    depth_of_cut: float = 1.2
    air_temperature: float = 300.1
    process_temperature: float = 310.1

    # Programmed setpoints. A CNC runs the feeds and speeds in its G-code;
    # live values jitter AROUND these, they do not wander off forever.
    nominal_spindle: float = 0.0
    nominal_torque: float = 0.0
    nominal_depth: float = 0.0

    source: str = "OPC UA"
    last_seen: str = ""

    tool_changes: List[ToolChangeEvent] = field(default_factory=list)
    acks: List[AlertAck] = field(default_factory=list)
    risk_history: List[float] = field(default_factory=list)
    smoothed_risk: Optional[float] = None
    fast_mode: bool = False

    # --- Flank-wear tracking (PHM 2010 model) ------------------------------
    # Running per-tool state. All of it resets on a tool change, because it
    # describes THIS insert's life and means nothing for the next one.
    wear_baseline: Dict[str, float] = field(default_factory=dict)
    wear_baseline_acc: List[Dict[str, float]] = field(default_factory=list)
    wear_cum_energy: float = 0.0
    wear_force_ewm: Optional[float] = None
    wear_vib_ewm: Optional[float] = None
    wear_windows_seen: int = 0
    wear_last_cut_s: float = 0.0
    predicted_wear_mm: Optional[float] = None
    wear_history: List[float] = field(default_factory=list)
    # Runtime (minutes) at which each wear_history point was recorded. Kept as
    # a parallel list so the pair (time, wear) can be regressed for remaining
    # useful life - a wear value with no timestamp cannot give a rate.
    wear_time_history: List[float] = field(default_factory=list)

    # Per-machine sensor character. Two identical machines never read
    # identically - fixture stiffness and sensor mounting differ - so each
    # machine gets a fixed offset. This is exactly the variation that makes
    # fresh-tool baselining necessary rather than optional.
    sensor_gain: float = 1.0

    def __post_init__(self):
        # Setpoints default to whatever the machine was created with
        if not self.nominal_spindle:
            self.nominal_spindle = self.spindle_speed or 1500.0
        if not self.nominal_torque:
            self.nominal_torque = self.spindle_torque or 40.0
        if not self.nominal_depth:
            self.nominal_depth = self.depth_of_cut or 1.2
        if self.sensor_gain == 1.0:
            # Deterministic per machine, so a restart does not change its character
            self.sensor_gain = 0.85 + (hash(self.machine_id) % 1000) / 1000.0 * 0.45

    # -----------------------------------------------------------------------
    # Flank-wear signal chain
    # -----------------------------------------------------------------------
    @property
    def wear_fraction(self) -> float:
        """How far through its nominal life this tool is, 0..1+."""
        return self.tool_runtime / NOMINAL_TOOL_LIFE_MIN

    @property
    def cut_seconds(self) -> float:
        """
        Cutting seconds since the last tool change, on the timescale the wear
        model was trained on. A real machine reports this straight from its
        spindle-on timer; the simulator derives it from accumulated runtime so
        the two clocks can never disagree.
        """
        return min(self.wear_fraction, 1.25) * PHM_TOOL_LIFE_S

    @property
    def replay_cutter(self) -> Optional[str]:
        """Which real PHM cutter this machine's signals are drawn from."""
        _load_replay()
        if not _REPLAY_CUTTERS:
            return None
        return _REPLAY_CUTTERS[hash(self.machine_id) % len(_REPLAY_CUTTERS)]

    def sensor_window_stats(self) -> Optional[Dict[str, float]]:
        """
        One window of condition-monitoring statistics for this machine.

        Demo path: read the real measured window from this machine's assigned
        PHM cutter, indexed by how far through its life the tool is, with a
        small per-machine gain so two machines running the same cutter are not
        bit-identical. Ratio features are unaffected by that gain, which is
        exactly why fresh-tool baselining is what makes the model portable.

        Production path: replace this method with the machine's live sensor
        feed and pass the samples through wear_features.window_stats().
        """
        if self.state != RUNNING:
            return None
        rep = _load_replay()
        cutter = self.replay_cutter
        if not cutter:
            return None

        stats_arr = rep[f"{cutter}__stats"]
        n = len(stats_arr)
        idx = int(max(0.0, min(self.wear_fraction, 0.999)) * n)
        row = stats_arr[min(idx, n - 1)]

        cols = raw_stat_columns()
        jitter = 1.0 + random.uniform(-0.02, 0.02)
        return {c: float(row[i]) * self.sensor_gain * jitter for i, c in enumerate(cols)}

    def observe_wear_window(self, stats: Optional[Dict[str, float]] = None) -> Optional[List[float]]:
        """
        Feed one window of sensor statistics through the wear feature chain and
        return the ordered feature vector, or None while the fresh-tool
        baseline is still being collected.

        Called once per tick for RUNNING machines. Owns the causal running
        state (baseline, cumulative energy, smoothed trends) that
        wear_features.build_feature_row() needs but cannot hold itself.
        Pass `stats` to drive it from a real sensor feed.
        """
        from utils.wear_features import build_feature_row   # local: avoids cycle

        if self.state != RUNNING:
            return None

        if stats is None:
            stats = self.sensor_window_stats()
        if stats is None:
            return None
        self.wear_windows_seen += 1

        # First ~30 s after a tool change defines this insert's baseline.
        if self.wear_windows_seen <= BASELINE_WINDOWS:
            self.wear_baseline_acc.append({c: stats[c] for c in raw_stat_columns()})
            n = len(self.wear_baseline_acc)
            self.wear_baseline = {
                c: sum(a[c] for a in self.wear_baseline_acc) / n
                for c in raw_stat_columns()
            }
            return None

        # Accumulate mechanical exposure per unit of CUTTING TIME, not per
        # call. The simulator ticks far more often per tool life than the
        # training data was windowed, so accumulating once per call would
        # inflate cumulative energy several-fold and push the feature outside
        # the range the model was fitted on. Scaling by elapsed cut time makes
        # the total independent of sampling rate - which is also the
        # physically correct statement, since energy is power times time.
        from utils.wear_features import WINDOW_SECONDS

        now_cut_s = self.cut_seconds
        elapsed = max(0.0, now_cut_s - self.wear_last_cut_s)
        self.wear_last_cut_s = now_cut_s
        self.wear_cum_energy += force_energy(stats) * (elapsed / WINDOW_SECONDS)

        self.wear_force_ewm = ewm_update(self.wear_force_ewm, stats["force_z_rms"])
        self.wear_vib_ewm = ewm_update(self.wear_vib_ewm, stats["vibration_z_rms"])

        return build_feature_row(
            stats, self.wear_baseline, self.wear_cum_energy,
            self.wear_force_ewm, self.wear_vib_ewm, self.cut_seconds,
        )

    def record_wear(self, wear_mm: float) -> float:
        """
        Store a wear prediction, enforcing that flank wear never decreases -
        abrasive wear is irreversible, so a dip can only be measurement noise.
        Returns the monotonic value actually recorded.
        """
        if self.predicted_wear_mm is not None:
            wear_mm = max(wear_mm, self.predicted_wear_mm)
        self.predicted_wear_mm = round(float(wear_mm), 4)
        self.wear_history.append(self.predicted_wear_mm)
        self.wear_time_history.append(round(self.tool_runtime, 3))
        self.wear_history = self.wear_history[-40:]
        self.wear_time_history = self.wear_time_history[-40:]
        return self.predicted_wear_mm

    def reset_wear_tracking(self):
        """Fresh insert: every per-tool wear signal starts over."""
        self.wear_baseline = {}
        self.wear_baseline_acc = []
        self.wear_cum_energy = 0.0
        self.wear_force_ewm = None
        self.wear_vib_ewm = None
        self.wear_windows_seen = 0
        self.wear_last_cut_s = 0.0
        self.predicted_wear_mm = None
        self.wear_history = []
        self.wear_time_history = []

    def step(self):
        """
        Advance one ~2s tick.

        Telemetry is mean-reverting around the programmed setpoint (an
        Ornstein-Uhlenbeck style walk) rather than a free random walk. A free
        walk drifts out of the model's training range within minutes and makes
        every machine read 99%, which is not a model problem - it is a
        simulator problem.

        The one real coupling: as a tool dulls it takes MORE torque to hold the
        same cut, so the feed/torque setpoint rises with accumulated runtime.
        That is why risk climbs with wear, and why it drops the moment a fresh
        tool is fitted.
        """
        self.last_seen = datetime.now(timezone.utc).isoformat()

        if self.state == OFFLINE:
            return

        if self.state in (IDLE, TOOL_CHANGE):
            # Spindle stopped. Telemetry decays, runtime frozen.
            self.spindle_speed = max(0.0, self.spindle_speed * 0.6)
            self.spindle_torque = max(0.0, self.spindle_torque * 0.6)
            self.process_temperature += (300.5 - self.process_temperature) * 0.05
            return

        # --- RUNNING -------------------------------------------------------
        # Dull tools draw more load: up to +30% torque near end of life.
        wear_ratio = min(self.tool_runtime / 220.0, 1.0)
        torque_target = self.nominal_torque * (1.0 + 0.30 * wear_ratio)
        spindle_target = self.nominal_spindle
        depth_target = self.nominal_depth

        def pull(current, target, jitter, k=0.12):
            """Pull toward target, then add bounded noise."""
            return current + (target - current) * k + random.uniform(-jitter, jitter)

        self.spindle_speed = max(600.0, min(pull(self.spindle_speed, spindle_target, 9.0), 2600.0))
        self.spindle_torque = max(5.0, min(pull(self.spindle_torque, torque_target, 0.7), 76.0))
        self.depth_of_cut = max(0.2, min(pull(self.depth_of_cut, depth_target, 0.02), 3.0))

        # Temperatures also revert, and rise slightly with load
        temp_target = 308.0 + (self.spindle_torque / 76.0) * 6.0
        self.process_temperature = pull(self.process_temperature, temp_target, 0.15)
        self.air_temperature = pull(self.air_temperature, 300.1, 0.06)

        self.tool_runtime += random.uniform(0.05, 0.15)

    def telemetry(self) -> dict:
        return {
            "spindle_speed": round(self.spindle_speed, 1),
            "spindle_torque": round(self.spindle_torque, 2),
            "tool_runtime": round(self.tool_runtime, 2),
            "depth_of_cut": round(self.depth_of_cut, 3),
            "air_temperature": round(self.air_temperature, 2),
            "process_temperature": round(self.process_temperature, 2),
            "material_type": self.material_type,
        }

    def log_tool_change(self, user: str, risk_at_change: float,
                        was_worn: Optional[bool], note: str = "") -> ToolChangeEvent:
        """
        The human-in-the-loop moment. Resets runtime to zero and captures
        whether the prediction was correct - a labelled row for retraining.
        """
        ev = ToolChangeEvent(
            event_id=f"tc-{uuid.uuid4().hex[:8]}",
            machine_id=self.machine_id,
            logged_by=user,
            logged_at=datetime.now(timezone.utc).isoformat(),
            runtime_at_change=round(self.tool_runtime, 2),
            predicted_risk_at_change=risk_at_change,
            was_actually_worn=was_worn,
            note=note,
        )
        self.tool_changes.append(ev)
        self.tool_runtime = 0.0                    # fresh tool
        self.spindle_torque = self.nominal_torque         # load drops back immediately
        self.risk_history = []
        self.smoothed_risk = None                       # old tool's trend is not this tool's
        self.reset_wear_tracking()                      # and neither is its wear curve
        self.state = RUNNING
        return ev

    def acknowledge(self, user: str, risk: float, decision: str, reason: str = "") -> AlertAck:
        ack = AlertAck(
            ack_id=f"ack-{uuid.uuid4().hex[:8]}",
            machine_id=self.machine_id,
            acked_by=user,
            acked_at=datetime.now(timezone.utc).isoformat(),
            risk_at_ack=risk,
            decision=decision,
            reason=reason,
        )
        self.acks.append(ack)
        return ack

    def to_json(self) -> str:
        """Serialize the full machine (including its event history) for
        the SQLite persistence layer in db.py."""
        return json.dumps(asdict(self))

    # Fields renamed after the initial release. The stored value is correct;
    # only the name was wrong - the column held spindle torque in Nm while
    # being called a feed rate, which is a different quantity in different
    # units. Machines saved before the rename are migrated on read.
    _RENAMED_FIELDS = {
        "feed_rate": "spindle_torque",
        "nominal_feed": "nominal_torque",
    }

    @classmethod
    def from_json(cls, raw: str) -> "Machine":
        d = json.loads(raw)
        for old, new in cls._RENAMED_FIELDS.items():
            if old in d:
                d.setdefault(new, d.pop(old))
        # Drop any key this version no longer knows about, so a machine saved
        # by a newer build never hard-crashes an older one.
        known = {f.name for f in fields(cls)}
        d = {k: v for k, v in d.items() if k in known}
        d["tool_changes"] = [ToolChangeEvent(**tc) for tc in d.get("tool_changes", [])]
        d["acks"] = [AlertAck(**a) for a in d.get("acks", [])]
        return cls(**d)


def seed_fleet(owner: str) -> Dict[str, Machine]:
    """
    Demo fleet for a freshly logged-in plant account.

    Deliberately mixed states - a shop where every machine is always
    running is a shop that does not exist.
    """
    return {
        m.machine_id: m for m in [
            Machine("m-01", "VMC-01 Haas VF2", owner, material_type="L",
                    state=RUNNING, tool_runtime=34, spindle_speed=1480,
                    spindle_torque=38, depth_of_cut=1.0, location="Bay 1",
                    source="MTConnect"),
            Machine("m-02", "VMC-02 Mazak VCN", owner, material_type="M",
                    state=RUNNING, tool_runtime=142, spindle_speed=1610,
                    spindle_torque=52, depth_of_cut=1.6, location="Bay 1",
                    source="OPC UA"),
            Machine("m-03", "VMC-03 DMG Mori", owner, material_type="H",
                    state=RUNNING, tool_runtime=205, spindle_speed=1720,
                    spindle_torque=61, depth_of_cut=1.9, location="Bay 2",
                    source="OPC UA"),
            Machine("m-04", "TC-01 Fanuc Robodrill", owner, material_type="M",
                    state=IDLE, tool_runtime=18, spindle_speed=0,
                    spindle_torque=0, depth_of_cut=1.1, location="Bay 2",
                    source="FOCAS"),
            Machine("m-05", "VMC-05 Hurco VM10", owner, material_type="L",
                    state=TOOL_CHANGE, tool_runtime=228, spindle_speed=0,
                    spindle_torque=0, depth_of_cut=1.4, location="Bay 3",
                    source="Retrofit sensor"),
            Machine("m-06", "VMC-06 Jyoti DX200", owner, material_type="M",
                    state=OFFLINE, tool_runtime=76, spindle_speed=0,
                    spindle_torque=0, depth_of_cut=1.2, location="Bay 3",
                    source="Retrofit sensor"),
        ]
    }