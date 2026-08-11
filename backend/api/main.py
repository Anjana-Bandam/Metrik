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
from datetime import datetime, timezone
from typing import Optional, List, Dict

import joblib
import numpy as np
import shap
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.sensor_config import resolve_features, SENSOR_CONFIG          # noqa: E402
from utils import auth as auth_mod                                        # noqa: E402
from utils.machine_state import (                                         # noqa: E402
    Machine, seed_fleet, STATE_LABELS, RUNNING, IDLE, TOOL_CHANGE, OFFLINE
)
from utils.tool_physics import (                                          # noqa: E402
    remaining_life_minutes, recommended_feed_override, physics_wear_risk
)  # noqa: E402
from utils.chatbot_mock import (                                          # noqa: E402
    narrative_for_machine, narrative_for_simulation, answer_question
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
    "Feed Rate [Nm]",
    "Cumulative Tool Runtime [min]",
    "Material Hardness Index",
    "Type_encoded",
]

model = scaler = type_encoder = explainer = None
MODEL_READY = False

try:
    model = joblib.load(os.path.join(MODELS_DIR, "metrik_xgb_model.pkl"))
    scaler = joblib.load(os.path.join(MODELS_DIR, "metrik_scaler.pkl"))
    type_encoder = joblib.load(os.path.join(MODELS_DIR, "metrik_type_encoder.pkl"))
    explainer = shap.TreeExplainer(model)
    MODEL_READY = True
    print("[Metrik] Model + SHAP explainer loaded.")
except FileNotFoundError:
    print("[Metrik] WARNING: artifacts missing. Run models/train_model.py. "
          "Using heuristic fallback so the API still boots.")

COST_PER_RISK_POINT = 1.5     # risk% * $150 / 100

# ---------------------------------------------------------------------------
# Per-account fleet storage
# ---------------------------------------------------------------------------
FLEETS: Dict[str, Dict[str, Machine]] = {}
SCRAP_SAVED: Dict[str, float] = {}

auth_mod.seed_demo_account()


def _ensure_fleet(username: str) -> Dict[str, Machine]:
    if username not in FLEETS:
        FLEETS[username] = seed_fleet(username)
        SCRAP_SAVED[username] = 4820.0
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
    role: Optional[str] = "operator"


class LoginRequest(BaseModel):
    username: str
    password: str


class SensorPayload(BaseModel):
    spindle_speed: Optional[float] = None
    feed_rate: Optional[float] = None
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


# ---------------------------------------------------------------------------
# Prediction core
# ---------------------------------------------------------------------------
def _heuristic_risk(features: dict) -> float:
    runtime = features.get("Cumulative Tool Runtime [min]", 100)
    feed = features.get("Feed Rate [Nm]", 40)
    return round(min(100.0, (runtime / 250) * 60 + (feed / 70) * 40), 1)


def run_prediction(payload: dict) -> dict:
    resolved = resolve_features(payload)
    features = resolved["features"]
    row = np.array([[features[c] for c in FEATURE_ORDER]])

    if MODEL_READY:
        scaled = scaler.transform(row)
        risk_pct = round(float(model.predict_proba(scaled)[0][1]) * 100, 1)
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
            {"feature": "Feed Rate [Nm]", "contribution_pct": 30.0, "direction": "increases risk"},
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
        feed_rate=features["Feed Rate [Nm]"],
    )

    # Second, independent signal: how much of the expected tool life is gone.
    physics_risk_pct = physics_wear_risk(life["life_consumed_pct"])

    # Combine with a noisy-OR. The tool is at risk if EITHER the live signature
    # looks abnormal OR it has exhausted its expected life - the two failure
    # routes are largely independent, so we don't average them (averaging would
    # let a normal-looking signature mask a tool that is 98% used up).
    combined = 1.0 - (1.0 - ml_risk_pct / 100.0) * (1.0 - physics_risk_pct / 100.0)
    risk_pct = round(min(combined * 100.0, 99.9), 1)

    status = "green" if risk_pct < 40 else "yellow" if risk_pct < 70 else "red"

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


def _snapshot(m: Machine, advance: bool = True) -> dict:
    if advance:
        m.step()

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
            payload["feed_rate"] = max(payload["feed_rate"], 20)
        prediction = run_prediction(payload)

    if m.state == RUNNING:
        m.risk_history.append(prediction["risk_pct"])
        m.risk_history = m.risk_history[-40:]

    narrative = narrative_for_machine(
        machine_name=m.name, risk_pct=prediction["risk_pct"],
        shap_values=prediction["shap_values"], life=prediction["life"],
        override=prediction["override"], state=m.state,
    )

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
        "risk_history": m.risk_history,
        "tool_changes": [t.__dict__ for t in m.tool_changes][-10:],
        "acks": [a.__dict__ for a in m.acks][-10:],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
@app.post("/auth/register")
def register(req: RegisterRequest):
    try:
        user = auth_mod.register(req.username, req.password, req.company,
                                 req.role, req.full_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    token = auth_mod.login(req.username, req.password)
    _ensure_fleet(user["username"])
    return {"token": token, "user": user}


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
        state=IDLE,               # a newly connected machine starts idle
        tool_runtime=0.0,         # fresh tool
        spindle_speed=1500.0, feed_rate=40.0, depth_of_cut=1.0,
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
    if req.was_actually_worn and snap["risk_pct"] >= 40:
        SCRAP_SAVED[user["username"]] = SCRAP_SAVED.get(user["username"], 0) + snap["cost_impact"]

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
    if not events:
        return {"total": 0, "correct": 0, "accuracy_pct": None, "events": []}

    correct = sum(1 for e in events
                  if (e.predicted_risk_at_change >= 40) == bool(e.was_actually_worn))
    return {
        "total": len(events),
        "correct": correct,
        "accuracy_pct": round(correct / len(events) * 100, 1),
        "events": [e.__dict__ for e in events][-20:],
    }


# ---------------------------------------------------------------------------
# Predict + chat
# ---------------------------------------------------------------------------
@app.post("/predict")
def predict(payload: SensorPayload):
    data = payload.model_dump()
    p = run_prediction(data)
    return {**p, "narrative": narrative_for_simulation(
        p["risk_pct"], p["shap_values"], p["life"], p["override"])}


@app.post("/chat")
def chat(req: ChatRequest, user: dict = Depends(current_user)):
    fleet = _ensure_fleet(user["username"])
    snapshots = [_snapshot(m, advance=False) for m in fleet.values()]
    machine = None
    if req.machine_id:
        machine = next((s for s in snapshots if s["machine_id"] == req.machine_id), None)
    return {"answer": answer_question(req.question, machine, snapshots)}


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