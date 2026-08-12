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

import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Dict, Optional

RUNNING = "RUNNING"
IDLE = "IDLE"
TOOL_CHANGE = "TOOL_CHANGE"
OFFLINE = "OFFLINE"

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
    feed_rate: float = 40.0
    tool_runtime: float = 0.0
    depth_of_cut: float = 1.2
    air_temperature: float = 300.1
    process_temperature: float = 310.1

    # Programmed setpoints. A CNC runs the feeds and speeds in its G-code;
    # live values jitter AROUND these, they do not wander off forever.
    nominal_spindle: float = 0.0
    nominal_feed: float = 0.0
    nominal_depth: float = 0.0

    source: str = "OPC UA"
    last_seen: str = ""

    tool_changes: List[ToolChangeEvent] = field(default_factory=list)
    acks: List[AlertAck] = field(default_factory=list)
    risk_history: List[float] = field(default_factory=list)
    smoothed_risk: Optional[float] = None
    fast_mode: bool = False

    def __post_init__(self):
        # Setpoints default to whatever the machine was created with
        if not self.nominal_spindle:
            self.nominal_spindle = self.spindle_speed or 1500.0
        if not self.nominal_feed:
            self.nominal_feed = self.feed_rate or 40.0
        if not self.nominal_depth:
            self.nominal_depth = self.depth_of_cut or 1.2

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
            self.feed_rate = max(0.0, self.feed_rate * 0.6)
            self.process_temperature += (300.5 - self.process_temperature) * 0.05
            return

        # --- RUNNING -------------------------------------------------------
        # Dull tools draw more load: up to +30% torque near end of life.
        wear_ratio = min(self.tool_runtime / 220.0, 1.0)
        feed_target = self.nominal_feed * (1.0 + 0.30 * wear_ratio)
        spindle_target = self.nominal_spindle
        depth_target = self.nominal_depth

        def pull(current, target, jitter, k=0.12):
            """Pull toward target, then add bounded noise."""
            return current + (target - current) * k + random.uniform(-jitter, jitter)

        self.spindle_speed = max(600.0, min(pull(self.spindle_speed, spindle_target, 9.0), 2600.0))
        self.feed_rate = max(5.0, min(pull(self.feed_rate, feed_target, 0.7), 76.0))
        self.depth_of_cut = max(0.2, min(pull(self.depth_of_cut, depth_target, 0.02), 3.0))

        # Temperatures also revert, and rise slightly with load
        temp_target = 308.0 + (self.feed_rate / 76.0) * 6.0
        self.process_temperature = pull(self.process_temperature, temp_target, 0.15)
        self.air_temperature = pull(self.air_temperature, 300.1, 0.06)

        self.tool_runtime += random.uniform(0.05, 0.15)

    def telemetry(self) -> dict:
        return {
            "spindle_speed": round(self.spindle_speed, 1),
            "feed_rate": round(self.feed_rate, 2),
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
        self.feed_rate = self.nominal_feed         # load drops back immediately
        self.risk_history = []
        self.smoothed_risk = None                       # old tool's trend is not this tool's
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
                    feed_rate=38, depth_of_cut=1.0, location="Bay 1",
                    source="MTConnect"),
            Machine("m-02", "VMC-02 Mazak VCN", owner, material_type="M",
                    state=RUNNING, tool_runtime=142, spindle_speed=1610,
                    feed_rate=52, depth_of_cut=1.6, location="Bay 1",
                    source="OPC UA"),
            Machine("m-03", "VMC-03 DMG Mori", owner, material_type="H",
                    state=RUNNING, tool_runtime=205, spindle_speed=1720,
                    feed_rate=61, depth_of_cut=1.9, location="Bay 2",
                    source="OPC UA"),
            Machine("m-04", "TC-01 Fanuc Robodrill", owner, material_type="M",
                    state=IDLE, tool_runtime=18, spindle_speed=0,
                    feed_rate=0, depth_of_cut=1.1, location="Bay 2",
                    source="FOCAS"),
            Machine("m-05", "VMC-05 Hurco VM10", owner, material_type="L",
                    state=TOOL_CHANGE, tool_runtime=228, spindle_speed=0,
                    feed_rate=0, depth_of_cut=1.4, location="Bay 3",
                    source="Retrofit sensor"),
            Machine("m-06", "VMC-06 Jyoti DX200", owner, material_type="M",
                    state=OFFLINE, tool_runtime=76, spindle_speed=0,
                    feed_rate=0, depth_of_cut=1.2, location="Bay 3",
                    source="Retrofit sensor"),
        ]
    }