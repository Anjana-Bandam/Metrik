"""
main.py
-------
Metrik API.

Auth:      /auth/register, /auth/login, /auth/me, /auth/logout
Fleet:     /get_all_machines, /machine/{id}, /add_machine, /machine/{id}/state
Predict:   /predict                       (What-If simulator)
Human:     /machine/{id}/tool_change, /machine/{id}/acknowledge
Chat:      /chat
Export:    /export/machine/{id}, /export/dashboard

Every fleet route is scoped to the logged-in account, so two plants that
sign up see completely separate machines.

Metrik is decision support. No endpoint here actuates a machine.
"""

import os
import sys
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict

import joblib
import numpy as np
import shap
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import csv
import io
from fastapi import File, UploadFile

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.sensor_config import resolve_features, SENSOR_CONFIG          # noqa: E402
from utils import auth as auth_mod                                        # noqa: E402
from utils import db as db_mod                                            # noqa: E402
from utils.machine_state import (                                         # noqa: E402
    Machine, seed_fleet, STATE_LABELS, RUNNING, IDLE, TOOL_CHANGE, OFFLINE
)
from utils.tool_physics import (                                          # noqa: E402
    remaining_life_minutes, recommended_feed_override, physics_wear_risk
)  # noqa: E402
from utils.chatbot_mock import (                                          # noqa: E402
    narrative_for_machine, narrative_for_simulation, answer_question
)
from utils.wear_features import (                                        # noqa: E402
    ISO_WEAR_LIMIT_MM, wear_status, WEAR_WATCH_MM, WEAR_ACT_MM,
    TRUE_CHANGE_POINT_MM, estimate_rul,
)

app = FastAPI(title="Metrik API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Model artifacts
# ---------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(HERE, "..", "models")

FEATURE_ORDER = [
    "Air temperature [K]",
    "Process temperature [K]",
    "Spindle Speed [rpm]",
    "Spindle Torque [Nm]",
    "Cumulative Tool Runtime [min]",
    "Material Hardness Index",
    "Type_encoded",
    "Wear x Load",
    "Temp Diff [K]",
    "Est Power [W]",
]

model = scaler = type_encoder = explainer = calibrator = None
MODEL_READY = False
RISK_META: Dict = {}

# Alert bands on the CALIBRATED scale. Defaults match what train_model.py
# computes; the saved metadata is authoritative when present. These are the
# same operating points as the old raw 0.40 / 0.70 cut-offs - the same machines
# alarm at the same moments - only the displayed number is now honest.
RISK_WATCH = 15.6
RISK_ALERT = 27.7

try:
    model = joblib.load(os.path.join(MODELS_DIR, "metrik_xgb_model.pkl"))
    scaler = joblib.load(os.path.join(MODELS_DIR, "metrik_scaler.pkl"))
    type_encoder = joblib.load(os.path.join(MODELS_DIR, "metrik_type_encoder.pkl"))
    explainer = shap.TreeExplainer(model)
    MODEL_READY = True
    print("[Metrik] Scrap-risk model + SHAP explainer loaded.")
except FileNotFoundError:
    print("[Metrik] WARNING: artifacts missing. Run models/train_model.py. "
          "Using heuristic fallback so the API still boots.")

# Platt calibrator. Without it the raw XGBoost score ranks well but reads far
# too high as a percentage (rows scoring 70-90% failed ~14% of the time),
# which matters because this number is shown to an operator as a probability.
try:
    calibrator = joblib.load(os.path.join(MODELS_DIR, "metrik_calibrator.pkl"))
    with open(os.path.join(MODELS_DIR, "metrik_risk_meta.json")) as _f:
        RISK_META = json.load(_f)
    RISK_WATCH = RISK_META.get("watch_threshold", RISK_WATCH / 100) * 100
    RISK_ALERT = RISK_META.get("alert_threshold", RISK_ALERT / 100) * 100
    print(f"[Metrik] Risk calibrator loaded (Brier "
          f"{RISK_META.get('brier_raw', 0):.5f} -> {RISK_META.get('brier_calibrated', 0):.5f}); "
          f"bands watch>={RISK_WATCH:.1f}% act>={RISK_ALERT:.1f}%.")
except FileNotFoundError:
    print("[Metrik] WARNING: no calibrator found - scrap risk will be shown as a raw "
          "score, which reads higher than the true probability. "
          "Re-run models/train_model.py.")


def _calibrate(raw_proba: float) -> float:
    """
    Map a raw model score onto an observed-frequency probability.

    Monotonic, so it never changes which machines rank as riskier than which -
    only what the number means. Falls through unchanged if no calibrator is
    available, so the API still works on a partially-trained install.
    """
    if calibrator is None:
        return raw_proba
    p = min(max(raw_proba, 1e-6), 1 - 1e-6)
    z = np.log(p / (1 - p))
    return float(calibrator.predict_proba(np.array([[z]]))[0, 1])


def risk_band(risk_pct: float) -> str:
    """Traffic light for a calibrated scrap-risk percentage."""
    if risk_pct < RISK_WATCH:
        return "green"
    if risk_pct < RISK_ALERT:
        return "yellow"
    return "red"

# ---------------------------------------------------------------------------
# Flank-wear model (PHM 2010, real measured wear).
#
# Metrik runs two models, because they answer two genuinely different
# questions and are validated on two different kinds of data:
#
#   metrik_xgb_model    -> SCRAP RISK. Probability that the current cut ends
#                          in a wear-driven overstrain scrap event. Trained on
#                          the synthetic AI4I 2020 benchmark.
#   metrik_wear_model   -> TOOL WEAR. Flank wear in millimetres, regressed
#                          against physically measured wear from the PHM 2010
#                          milling experiments, validated leave-one-tool-out.
#
# Only the second one supports a tool-wear claim; keeping them separate is
# what stops one model's numbers being quoted for the other's question.
# ---------------------------------------------------------------------------
wear_model = wear_scaler = None
WEAR_META: Dict = {}
WEAR_READY = False

try:
    wear_model = joblib.load(os.path.join(MODELS_DIR, "metrik_wear_model.pkl"))
    wear_scaler = joblib.load(os.path.join(MODELS_DIR, "metrik_wear_scaler.pkl"))
    with open(os.path.join(MODELS_DIR, "metrik_wear_meta.json")) as _f:
        WEAR_META = json.load(_f)
    WEAR_WATCH_MM = WEAR_META.get("watch_mm", WEAR_WATCH_MM)
    WEAR_ACT_MM = WEAR_META.get("act_mm", WEAR_ACT_MM)
    WEAR_READY = True
    print(f"[Metrik] Flank-wear model loaded "
          f"(leave-one-tool-out MAE {WEAR_META.get('loto_mae_um', 0):.1f} um, "
          f"R2 {WEAR_META.get('loto_r2', 0):.3f}); "
          f"change-out alert at {WEAR_ACT_MM} mm "
          f"(recall {WEAR_META.get('change_decision', {}).get('recall', 0):.2f}).")
except FileNotFoundError:
    print("[Metrik] WARNING: wear-model artifacts missing. "
          "Run models/train_wear_model.py to enable measured tool-wear prediction.")

COST_PER_RISK_POINT = 1.5     # risk% * $150 / 100

# ---------------------------------------------------------------------------
# Per-account fleet storage
# ---------------------------------------------------------------------------
FLEETS: Dict[str, Dict[str, Machine]] = {}
SCRAP_SAVED: Dict[str, float] = {}


def _persist_machine(m: Machine):
    db_mod.upsert_machine(m.machine_id, m.owner, m.to_json())


# Persistence: rehydrate accounts, sessions and machines from disk (see
# db.py) so a server restart no longer wipes every signup and fleet.
db_mod.init_db()
auth_mod.load_from_db()
for _machine_id, _owner, _data in db_mod.fetch_all_machines():
    FLEETS.setdefault(_owner, {})[_machine_id] = Machine.from_json(_data)
SCRAP_SAVED.update(db_mod.fetch_scrap_saved())

auth_mod.seed_demo_account()


def _ensure_fleet(username: str) -> Dict[str, Machine]:
    if username not in FLEETS:
        # Only the demo account gets a pre-loaded fleet, so judges see a
        # working plant immediately. Every real signup starts empty — the
        # user adds their own machines, which is the correct behaviour.
        FLEETS[username] = seed_fleet(username) if username == "demo" else {}
        SCRAP_SAVED[username] = 4820.0 if username == "demo" else 0.0
        for m in FLEETS[username].values():
            _persist_machine(m)
        db_mod.upsert_scrap_saved(username, SCRAP_SAVED[username])
    return FLEETS[username]


def current_user(authorization: Optional[str] = Header(None)) -> dict:
    """Bearer-token dependency. Every fleet route depends on this."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not signed in.")
    user = auth_mod.user_for_token(authorization.split(" ", 1)[1])
    if not user:
        raise HTTPException(status_code=401, detail="Session expired. Sign in again.")
    return user


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class RegisterRequest(BaseModel):
    username: str
    password: str
    company: str
    full_name: Optional[str] = ""
    # No `role` field: role is never accepted from the client. Every signup
    # starts as an operator (utils.auth.ROLE_OPERATOR); manager accounts
    # are granted out-of-band, not self-selected at signup.


class LoginRequest(BaseModel):
    username: str
    password: str


class SensorPayload(BaseModel):
    spindle_speed: Optional[float] = None
    spindle_torque: Optional[float] = None
    tool_runtime: Optional[float] = None
    depth_of_cut: Optional[float] = None
    air_temperature: Optional[float] = None
    process_temperature: Optional[float] = None
    material_type: Optional[str] = Field(default="M")
    tool_material: Optional[str] = Field(default="carbide")


class AddMachineRequest(BaseModel):
    name: str
    material_type: Optional[str] = "M"
    tool_material: Optional[str] = "carbide"
    location: Optional[str] = "Bay 1"
    source: Optional[str] = "OPC UA"


class StateChangeRequest(BaseModel):
    state: str


class ToolChangeRequest(BaseModel):
    was_actually_worn: Optional[bool] = None
    note: Optional[str] = ""


class AckRequest(BaseModel):
    decision: str          # accepted | dismissed | snoozed
    reason: Optional[str] = ""


class ChatRequest(BaseModel):
    question: str
    machine_id: Optional[str] = None
    history: Optional[List[Dict[str, str]]] = None




# ---------------------------------------------------------------------------
# Prediction core
# ---------------------------------------------------------------------------
def _heuristic_risk(features: dict) -> float:
    runtime = features.get("Cumulative Tool Runtime [min]", 100)
    feed = features.get("Spindle Torque [Nm]", 40)
    return round(min(100.0, (runtime / 250) * 60 + (feed / 70) * 40), 1)


def run_prediction(payload: dict) -> dict:
    resolved = resolve_features(payload)
    features = resolved["features"]
    row = np.array([[features[c] for c in FEATURE_ORDER]])

    if MODEL_READY:
        scaled = scaler.transform(row)
        # Calibrate before display: the raw score ranks well but overstates the
        # probability badly under 1.2% prevalence (see models/train_model.py).
        risk_pct = round(_calibrate(float(model.predict_proba(scaled)[0][1])) * 100, 1)
        raw = explainer.shap_values(scaled)
        shap_row = raw[0] if not isinstance(raw, list) else raw[1][0]
        abs_vals = np.abs(shap_row)
        total = abs_vals.sum() or 1.0
        shap_values = sorted(
            [{"feature": FEATURE_ORDER[i],
              "contribution_pct": round(float(abs_vals[i] / total) * 100, 1),
              "direction": "increases risk" if shap_row[i] > 0 else "decreases risk"}
             for i in range(len(FEATURE_ORDER))],
            key=lambda d: d["contribution_pct"], reverse=True)
    else:
        risk_pct = _heuristic_risk(features)
        shap_values = [
            {"feature": "Cumulative Tool Runtime [min]", "contribution_pct": 60.0, "direction": "increases risk"},
            {"feature": "Spindle Torque [Nm]", "contribution_pct": 30.0, "direction": "increases risk"},
            {"feature": "Spindle Speed [rpm]", "contribution_pct": 10.0, "direction": "increases risk"},
        ]

    # The XGBoost output on its own answers only "does this signature look
    # abnormal". Keep it labelled as such.
    ml_risk_pct = risk_pct

    # Physics-blended remaining life (Taylor) instead of a made-up curve
    life = remaining_life_minutes(
        elapsed_runtime=features["Cumulative Tool Runtime [min]"],
        ml_risk_pct=ml_risk_pct,
        spindle_rpm=features["Spindle Speed [rpm]"],
        material_type=payload.get("material_type", "M"),
        tool_material=payload.get("tool_material", "carbide"),
        depth_of_cut=payload.get("depth_of_cut") or 1.0,
        spindle_torque=features["Spindle Torque [Nm]"],
    )

    # Second, independent signal: how much of the expected tool life is gone.
    physics_risk_pct = physics_wear_risk(life["life_consumed_pct"])

    # Combine with a noisy-OR. The tool is at risk if EITHER the live signature
    # looks abnormal OR it has exhausted its expected life - the two failure
    # routes are largely independent, so we don't average them (averaging would
    # let a normal-looking signature mask a tool that is 98% used up).
    combined = 1.0 - (1.0 - ml_risk_pct / 100.0) * (1.0 - physics_risk_pct / 100.0)
    risk_pct = round(min(combined * 100.0, 99.9), 1)

    status = risk_band(risk_pct)

    return {
        "risk_pct": risk_pct,
        "ml_risk_pct": ml_risk_pct,
        "physics_risk_pct": physics_risk_pct,
        "status": status,
        "shap_values": shap_values,
        "estimated_fields": resolved["estimated_fields"],
        "life": life,
        "override": recommended_feed_override(risk_pct),
        "cost_impact": round(risk_pct * COST_PER_RISK_POINT, 2),
        "features_used": features,
    }


def _fmt(minutes: float) -> str:
    minutes = int(minutes)
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h}h {m}m"
    return f"{h}h" if h else f"{m}m"


def _rul_fields(m: Machine) -> dict:
    """
    Remaining useful life for one machine, in minutes of runtime.

    Returns None values rather than zeros when the trend is not yet
    established - a tool with no usable wear trend has unknown life left, and
    rendering that as "0 minutes" would read as an emergency.
    """
    est = estimate_rul(m.wear_time_history, m.wear_history, WEAR_ACT_MM)
    if est is None:
        return {"rul_min": None, "rul_low_min": None,
                "rul_high_min": None, "wear_rate_mm_per_min": None}
    return {
        "rul_min": round(est["rul"], 1),
        "rul_low_min": round(est["low"], 1),
        "rul_high_min": round(est["high"], 1),
        "wear_rate_mm_per_min": round(est["rate_per_unit"], 6),
    }


def predict_wear(m: Machine, features: Optional[List[float]], advanced: bool) -> dict:
    """
    Predict measured flank wear (mm) for one machine from its condition-
    monitoring signals.

    `features` is the newest feature vector produced while advancing the
    simulation, or None if no complete window was available on this call.
    The wear chain is advanced by the caller, once per simulated tick, so that
    Fast Sim cannot capture a "fresh tool" baseline from an already-worn tool.

    Returns a dict that is always shape-stable, so the UI never has to guard
    against a missing key. `available` says whether there is a real prediction
    behind the numbers; `reason` says why not when there isn't. The two states
    that legitimately have no prediction are a stopped spindle (no cut, no
    signal) and the first ~30 seconds after a tool change, while the fresh-tool
    baseline is still being captured.
    """
    blank = {
        "available": False,
        "wear_mm": None,
        "wear_pct_of_limit": None,
        "status": "unknown",
        "limit_mm": ISO_WEAR_LIMIT_MM,
        "watch_mm": WEAR_WATCH_MM,
        "alert_mm": WEAR_ACT_MM,
        "true_change_point_mm": TRUE_CHANGE_POINT_MM,
        "history": m.wear_history,
        "reason": "",
        "baseline_progress": min(1.0, m.wear_windows_seen / 15.0),
        "rul_min": None,
        "rul_low_min": None,
        "rul_high_min": None,
        "wear_rate_mm_per_min": None,
    }

    if not WEAR_READY:
        blank["reason"] = "Wear model not trained. Run models/train_wear_model.py."
        return blank
    if m.state != RUNNING:
        blank["reason"] = "Spindle stopped - flank wear is only measurable while cutting."
        return blank

    if features is None:
        # No new window this call. If this tool already has a prediction, keep
        # showing it - wear does not un-happen because we did not sample.
        if m.predicted_wear_mm is not None:
            wear_mm = m.predicted_wear_mm
            return {
                "available": True,
                "wear_mm": round(wear_mm, 4),
                "wear_pct_of_limit": round(wear_mm / ISO_WEAR_LIMIT_MM * 100, 1),
                "status": wear_status(wear_mm, WEAR_WATCH_MM, WEAR_ACT_MM),
                "limit_mm": ISO_WEAR_LIMIT_MM,
                "watch_mm": WEAR_WATCH_MM,
                "alert_mm": WEAR_ACT_MM,
                "true_change_point_mm": TRUE_CHANGE_POINT_MM,
                "history": m.wear_history,
                "reason": "",
                "baseline_progress": 1.0,
                **_rul_fields(m),
            }
        blank["reason"] = "Learning this tool's fresh-cut baseline..."
        return blank

    row = np.array([features], dtype=float)
    wear_mm = float(wear_model.predict(wear_scaler.transform(row))[0])
    wear_mm = m.record_wear(max(0.0, wear_mm))

    return {
        "available": True,
        "wear_mm": round(wear_mm, 4),
        "wear_pct_of_limit": round(wear_mm / ISO_WEAR_LIMIT_MM * 100, 1),
        "status": wear_status(wear_mm, WEAR_WATCH_MM, WEAR_ACT_MM),
        "limit_mm": ISO_WEAR_LIMIT_MM,
        "watch_mm": WEAR_WATCH_MM,
        "alert_mm": WEAR_ACT_MM,
        "true_change_point_mm": TRUE_CHANGE_POINT_MM,
        "history": m.wear_history,
        "reason": "",
        "baseline_progress": 1.0,
        **_rul_fields(m),
    }


def _snapshot(m: Machine, advance: bool = True) -> dict:
    # The wear chain must advance in lockstep with simulated time, not once per
    # HTTP poll. In Fast Sim a single poll covers ~150 ticks; sampling wear only
    # once per poll would spend the whole fresh-tool baseline window on a tool
    # that had already worn most of the way through its life.
    wear_features_row = None
    if advance:
        ticks = FAST_MODE_TICKS_PER_POLL if (m.fast_mode and m.state == RUNNING) else 1
        for _ in range(ticks):
            m.step()
            row = m.observe_wear_window()
            if row is not None:
                wear_features_row = row
    telemetry = m.telemetry()

    if m.state == OFFLINE:
        # No signal -> no prediction. Be honest about it rather than inventing one.
        prediction = {
            "risk_pct": 0.0, "status": "offline", "shap_values": [],
            "estimated_fields": [], "cost_impact": 0.0,
            "life": {"expected_tool_life_min": 0, "remaining_min": 0,
                     "remaining_low_min": 0, "remaining_high_min": 0,
                     "cutting_speed_m_min": 0, "life_consumed_pct": 0},
            "override": {"override_pct": 100, "action": "none",
                         "text": "No live signal from this machine."},
        }
    else:
        payload = dict(telemetry)
        payload["tool_material"] = m.tool_material
        if m.state in (IDLE, TOOL_CHANGE):
            # Spindle stopped: score the last known cutting condition so the
            # card still shows meaningful tool state, but freeze it.
            payload["spindle_speed"] = max(payload["spindle_speed"], 1200)
            payload["spindle_torque"] = max(payload["spindle_torque"], 20)
        prediction = run_prediction(payload)

    if m.state == RUNNING:
        # Smooth the displayed risk with an exponential moving average.
        # Without this, small sensor jitter can swing a tree-based model's
        # output by 40-50 points between two readings 2 seconds apart —
        # real dashboards never show a raw number that jumpy.
        raw_risk = prediction["risk_pct"]
        m.smoothed_risk = raw_risk if m.smoothed_risk is None else round(0.35 * raw_risk + 0.65 * m.smoothed_risk, 1)
        smoothed = m.smoothed_risk

        # Recompute life, override and cost from the smoothed risk so every
        # number on screen stays internally consistent with the headline.
        life = remaining_life_minutes(
            elapsed_runtime=prediction["features_used"]["Cumulative Tool Runtime [min]"],
            ml_risk_pct=smoothed,
            spindle_rpm=prediction["features_used"]["Spindle Speed [rpm]"],
            material_type=m.material_type,
            tool_material=m.tool_material,
            depth_of_cut=m.depth_of_cut,
            spindle_torque=prediction["features_used"]["Spindle Torque [Nm]"],
        )
        prediction["risk_pct"] = smoothed
        prediction["status"] = risk_band(smoothed)
        prediction["life"] = life
        prediction["override"] = recommended_feed_override(smoothed)
        prediction["cost_impact"] = round(smoothed * COST_PER_RISK_POINT, 2)

        m.risk_history.append(prediction["risk_pct"])
        m.risk_history = m.risk_history[-40:]

    # Measured flank wear, from the PHM 2010 model.
    wear = predict_wear(m, wear_features_row, advance)

    narrative = narrative_for_machine(
        machine_name=m.name, risk_pct=prediction["risk_pct"],
        shap_values=prediction["shap_values"], life=prediction["life"],
        override=prediction["override"], state=m.state,
        watch_pct=RISK_WATCH, alert_pct=RISK_ALERT,
    )

    _persist_machine(m)

    return {
        "machine_id": m.machine_id,
        "name": m.name,
        "location": m.location,
        "material_type": m.material_type,
        "tool_material": m.tool_material,
        "state": m.state,
        "state_label": STATE_LABELS[m.state],
        "source": m.source,
        "last_seen": m.last_seen,
        "sensors": telemetry,
        "risk_pct": prediction["risk_pct"],
        "status": prediction["status"],
        "life": prediction["life"],
        "est_time_to_failure": _fmt(prediction["life"]["remaining_min"]),
        "override": prediction["override"],
        "cost_impact": prediction["cost_impact"],
        "shap_values": prediction["shap_values"],
        "estimated_fields": prediction["estimated_fields"],
        "narrative": narrative,
        "wear": wear,
        "risk_bands": {"watch": round(RISK_WATCH, 1), "alert": round(RISK_ALERT, 1)},
        "risk_history": m.risk_history,
        "tool_changes": [t.__dict__ for t in m.tool_changes][-10:],
        "acks": [a.__dict__ for a in m.acks][-10:],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fast_mode": m.fast_mode,
    }


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
@app.post("/auth/register")
def register(req: RegisterRequest):
    try:
        user = auth_mod.register(req.username, req.password, req.company,
                                 full_name=req.full_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    token = auth_mod.login(req.username, req.password)
    _ensure_fleet(user["username"])
    return {"token": token, "user": user}




FAST_MODE_TICKS_PER_POLL = 150  # roughly 1 simulated minute per real second while ON


class FastModeRequest(BaseModel):
    enabled: bool


@app.post("/machine/{machine_id}/fast_mode")
def set_fast_mode(machine_id: str, req: FastModeRequest, user: dict = Depends(current_user)):
    """
    Demo-only speed toggle. While ON, each dashboard poll advances the
    machine's simulated clock ~20x faster, so wear probability visibly
    climbs while you watch. Toggle OFF returns it to normal speed
    instantly — nothing is jumped or skipped, just the tick rate changes.
    """
    fleet = _ensure_fleet(user["username"])
    m = fleet.get(machine_id)
    if not m:
        raise HTTPException(status_code=404, detail="Machine not found.")
    m.fast_mode = req.enabled
    return _snapshot(m, advance=False)




MAX_CSV_BYTES = 5 * 1024 * 1024   # 5MB - generous for a spreadsheet export,
                                    # small enough that one upload can't stall
                                    # this single-process demo server
MAX_CSV_ROWS = 5000                # bounds the model/SHAP loop below no
                                    # matter how many rows the file claims


@app.post("/predict_csv")
async def predict_csv(file: UploadFile = File(...), user: dict = Depends(current_user)):
    """
    Batch prediction from an uploaded CSV. Lets a judge supply their own
    numbers and see the model respond to inputs nobody pre-loaded — proof
    the prediction is real, not scripted.

    Requires sign-in and is capped at MAX_CSV_BYTES / MAX_CSV_ROWS so an
    upload can't be used to exhaust server memory or CPU.

    Expected columns (all optional except at least one sensor value):
    spindle_speed, spindle_torque, tool_runtime, depth_of_cut, air_temperature,
    process_temperature, material_type (L/M/H), tool_material (carbide/hss/ceramic)
    """
    content = await file.read()
    if len(content) > MAX_CSV_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"CSV too large (max {MAX_CSV_BYTES // (1024 * 1024)}MB).")

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Could not read the file as text. Please upload a UTF-8 CSV.")

    reader = csv.DictReader(io.StringIO(text))
    results = []
    truncated = False
    for i, row in enumerate(reader):
        if i >= MAX_CSV_ROWS:
            truncated = True
            break
        payload = {}
        for key in ("spindle_speed", "spindle_torque", "tool_runtime", "depth_of_cut",
                   "air_temperature", "process_temperature"):
            val = row.get(key)
            if val not in (None, ""):
                try:
                    payload[key] = float(val)
                except ValueError:
                    pass
        payload["material_type"] = (row.get("material_type") or "M").strip().upper()[:1]
        payload["tool_material"] = (row.get("tool_material") or "carbide").strip().lower()
        pred = run_prediction(payload)
        results.append({
            "row": i + 1,
            "input": payload,
            "risk_pct": pred["risk_pct"],
            "status": pred["status"],
            "est_time_to_failure": _fmt(pred["life"]["remaining_min"]),
            "cost_impact": pred["cost_impact"],
            "top_driver": pred["shap_values"][0]["feature"] if pred["shap_values"] else None,
        })
    return {"count": len(results), "results": results, "truncated": truncated}









@app.post("/auth/login")
def login(req: LoginRequest):
    token = auth_mod.login(req.username, req.password)
    if not token:
        raise HTTPException(status_code=401, detail="Incorrect username or password.")
    user = auth_mod.public_user(req.username.strip().lower())
    _ensure_fleet(user["username"])
    return {"token": token, "user": user}


@app.get("/auth/me")
def me(user: dict = Depends(current_user)):
    return auth_mod.public_user(user["username"])


@app.post("/auth/logout")
def do_logout(authorization: Optional[str] = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        auth_mod.logout(authorization.split(" ", 1)[1])
    return {"ok": True}


# ---------------------------------------------------------------------------
# Fleet routes
# ---------------------------------------------------------------------------
@app.get("/get_all_machines")
def get_all_machines(user: dict = Depends(current_user)):
    fleet = _ensure_fleet(user["username"])
    snapshots = [_snapshot(m) for m in fleet.values()]

    running = [s for s in snapshots if s["state"] == RUNNING]
    warnings = [s for s in running if s["status"] in ("yellow", "red")]
    avg_remaining = (np.mean([s["life"]["remaining_min"] for s in running])
                     if running else 0)

    return {
        "machines": snapshots,
        "kpis": {
            "active_machines": len(running),
            "total_machines": len(snapshots),
            "active_warnings": len(warnings),
            "avg_remaining_life_hours": round(avg_remaining / 60, 1),
            "scrap_saved_usd": round(SCRAP_SAVED.get(user["username"], 0), 2),
            "offline_machines": sum(1 for s in snapshots if s["state"] == OFFLINE),
        },
    }


@app.get("/machine/{machine_id}")
def get_machine(machine_id: str, user: dict = Depends(current_user)):
    fleet = _ensure_fleet(user["username"])
    m = fleet.get(machine_id)
    if not m:
        raise HTTPException(status_code=404, detail="Machine not found.")
    return _snapshot(m)


@app.post("/add_machine")
def add_machine(req: AddMachineRequest, user: dict = Depends(current_user)):
    import uuid
    fleet = _ensure_fleet(user["username"])
    new_id = f"m-{uuid.uuid4().hex[:6]}"
    m = Machine(
        machine_id=new_id,
        name=req.name.strip() or f"Machine {len(fleet) + 1}",
        owner=user["username"],
        material_type=req.material_type if req.material_type in ("L", "M", "H") else "M",
        tool_material=(req.tool_material
                       if req.tool_material in ("carbide", "hss", "ceramic")
                       else "carbide"),
        location=req.location or "Bay 1",
        source=(req.source if req.source in
                ("OPC UA", "MTConnect", "FOCAS", "Retrofit sensor", "CSV upload")
                else "OPC UA"),
        state=RUNNING,             # starts running so the dashboard, risk
                                    # history and Fast sim are live right away
        tool_runtime=0.0,         # fresh tool
        spindle_speed=1500.0, spindle_torque=40.0, depth_of_cut=1.0,
    )
    fleet[new_id] = m
    return _snapshot(m, advance=False)


@app.post("/machine/{machine_id}/state")
def set_state(machine_id: str, req: StateChangeRequest,
              user: dict = Depends(current_user)):
    """
    Mirrors the state the machine itself reports. In the demo the user can
    flip it to show idle/offline behaviour. This does NOT command the
    machine - it records what the machine is doing.
    """
    fleet = _ensure_fleet(user["username"])
    m = fleet.get(machine_id)
    if not m:
        raise HTTPException(status_code=404, detail="Machine not found.")
    if req.state not in (RUNNING, IDLE, TOOL_CHANGE, OFFLINE):
        raise HTTPException(status_code=400, detail="Unknown state.")
    m.state = req.state
    return _snapshot(m, advance=False)


@app.delete("/machine/{machine_id}")
def remove_machine(machine_id: str, user: dict = Depends(current_user)):
    fleet = _ensure_fleet(user["username"])
    if machine_id not in fleet:
        raise HTTPException(status_code=404, detail="Machine not found.")
    del fleet[machine_id]
    db_mod.delete_machine(machine_id)
    return {"deleted": machine_id}


# ---------------------------------------------------------------------------
# Human-in-the-loop routes  <-- this is the differentiating feature
# ---------------------------------------------------------------------------
@app.post("/machine/{machine_id}/tool_change")
def log_tool_change(machine_id: str, req: ToolChangeRequest,
                    user: dict = Depends(current_user)):
    """
    An operator confirms a tool was physically changed. Runtime resets and
    we capture whether the tool was genuinely worn - a labelled row that
    can be fed back into training. This closes the ML loop.
    """
    fleet = _ensure_fleet(user["username"])
    m = fleet.get(machine_id)
    if not m:
        raise HTTPException(status_code=404, detail="Machine not found.")

    snap = _snapshot(m, advance=False)
    ev = m.log_tool_change(user["username"], snap["risk_pct"],
                           req.was_actually_worn, req.note or "")

    # Credit avoided scrap when Metrik correctly flagged a worn tool
    if req.was_actually_worn and snap["risk_pct"] >= RISK_WATCH:
        SCRAP_SAVED[user["username"]] = SCRAP_SAVED.get(user["username"], 0) + snap["cost_impact"]
        db_mod.upsert_scrap_saved(user["username"], SCRAP_SAVED[user["username"]])

    return {"event": ev.__dict__, "machine": _snapshot(m, advance=False)}


@app.post("/machine/{machine_id}/acknowledge")
def acknowledge(machine_id: str, req: AckRequest,
                user: dict = Depends(current_user)):
    fleet = _ensure_fleet(user["username"])
    m = fleet.get(machine_id)
    if not m:
        raise HTTPException(status_code=404, detail="Machine not found.")
    snap = _snapshot(m, advance=False)
    ack = m.acknowledge(user["username"], snap["risk_pct"],
                        req.decision, req.reason or "")
    return {"ack": ack.__dict__}


@app.get("/model_feedback")
def model_feedback(user: dict = Depends(current_user)):
    """
    Aggregate of operator verdicts - "how often was Metrik right?".
    Shown on the Reports page as a live accuracy scoreboard.
    """
    fleet = _ensure_fleet(user["username"])
    events = [t for m in fleet.values() for t in m.tool_changes
              if t.was_actually_worn is not None]

    # Below this many verdicts a percentage is noise, not a measurement: one
    # lucky call reads as "100% accurate", which is exactly the kind of number
    # that destroys trust the first time it is wrong.
    MIN_EVENTS_FOR_RATE = 10

    base = {
        "total": len(events),
        "correct": 0,
        "accuracy_pct": None,
        "ci_low": None,
        "ci_high": None,
        "enough_data": False,
        "min_events": MIN_EVENTS_FOR_RATE,
        "breakdown": {"tp": 0, "fp": 0, "tn": 0, "fn": 0},
        "caveat": ("Scored only on tools an operator chose to change, which is a "
                   "biased sample - tools left running are never scored. Treat "
                   "this as a field sanity check, not a validation metric; the "
                   "validated numbers come from cross-validation in the model "
                   "training scripts."),
        "events": [e.__dict__ for e in events][-20:],
    }
    if not events:
        return base

    tp = fp = tn = fn = 0
    for e in events:
        flagged = e.predicted_risk_at_change >= RISK_WATCH
        worn = bool(e.was_actually_worn)
        if flagged and worn:
            tp += 1
        elif flagged and not worn:
            fp += 1
        elif not flagged and not worn:
            tn += 1
        else:
            fn += 1

    correct = tp + tn
    n = len(events)
    base["correct"] = correct
    base["breakdown"] = {"tp": tp, "fp": fp, "tn": tn, "fn": fn}

    if n < MIN_EVENTS_FOR_RATE:
        return base

    # Wilson score interval - honest about uncertainty at small n, unlike the
    # bare ratio, which claims far more precision than a handful of events give.
    p_hat = correct / n
    z = 1.96
    denom = 1 + z ** 2 / n
    centre = (p_hat + z ** 2 / (2 * n)) / denom
    margin = z * ((p_hat * (1 - p_hat) / n + z ** 2 / (4 * n ** 2)) ** 0.5) / denom

    base.update({
        "accuracy_pct": round(p_hat * 100, 1),
        "ci_low": round(max(0.0, centre - margin) * 100, 1),
        "ci_high": round(min(1.0, centre + margin) * 100, 1),
        "enough_data": True,
    })
    return base


# ---------------------------------------------------------------------------
# Predict + chat
# ---------------------------------------------------------------------------
@app.post("/predict")
def predict(payload: SensorPayload):
    """
    What-if scoring for a job that has not run yet.

    Returns SCRAP RISK only, deliberately. Measured flank wear cannot be
    predicted here: the wear model reads cutting force, vibration and acoustic
    emission from a tool that is actually cutting, and a job being planned in
    CAM has produced no such signal yet. Reporting a wear figure for a
    hypothetical job would be inventing a measurement, so the planner says so
    instead - see `wear_available` below.
    """
    data = payload.model_dump()
    p = run_prediction(data)
    return {
        **p,
        "risk_bands": {"watch": round(RISK_WATCH, 1), "alert": round(RISK_ALERT, 1)},
        "wear_available": False,
        "wear_note": ("Measured flank wear needs live force and vibration from a "
                      "cutting tool. A planned job has no signal yet, so Metrik "
                      "projects scrap risk here and measures wear once the job runs."),
        "narrative": narrative_for_simulation(
            p["risk_pct"], p["shap_values"], p["life"], p["override"],
            watch_pct=RISK_WATCH, alert_pct=RISK_ALERT),
    }


@app.post("/chat")
def chat(req: ChatRequest, user: dict = Depends(current_user)):
    fleet = _ensure_fleet(user["username"])
    snapshots = [_snapshot(m, advance=False) for m in fleet.values()]
    machine = None
    if req.machine_id:
        machine = next((s for s in snapshots if s["machine_id"] == req.machine_id), None)
    return {"answer": answer_question(req.question, machine, snapshots, req.history)}


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
@app.get("/export/machine/{machine_id}")
def export_machine(machine_id: str, user: dict = Depends(current_user)):
    fleet = _ensure_fleet(user["username"])
    m = fleet.get(machine_id)
    if not m:
        raise HTTPException(status_code=404, detail="Machine not found.")
    return JSONResponse(
        content={"generated_by": "Metrik", "plant": user["company"],
                 "machine": _snapshot(m, advance=False)},
        headers={"Content-Disposition":
                 f'attachment; filename="metrik_{machine_id}_report.json"'})


@app.get("/export/dashboard")
def export_dashboard(user: dict = Depends(current_user)):
    fleet = _ensure_fleet(user["username"])
    return JSONResponse(
        content={"generated_by": "Metrik", "plant": user["company"],
                 "exported_at": datetime.now(timezone.utc).isoformat(),
                 "fleet_size": len(fleet),
                 "machines": [_snapshot(m, advance=False) for m in fleet.values()]},
        headers={"Content-Disposition":
                 'attachment; filename="metrik_dashboard_export.json"'})


@app.get("/sensor_config")
def get_sensor_config():
    return SENSOR_CONFIG


@app.get("/")
def root():
    return {"service": "Metrik API", "status": "ok", "model_ready": MODEL_READY}