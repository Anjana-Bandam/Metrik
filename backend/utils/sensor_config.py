"""
sensor_config.py
------------------
"Sensor Flexibility" edge case handling.

Real CNC shops don't all have the same sensor package. A machine might
be missing a torque sensor, a temperature probe, or report runtime in
a different unit. Metrik must NEVER crash because of a missing field -
it should degrade gracefully using a documented fallback strategy.

SENSOR_CONFIG describes, for every feature the model needs:
  - the JSON key the frontend / simulator sends it as
  - whether it's required
  - a fallback strategy if it's missing: "median" (use the training
    median) or "derive" (estimate it from other available sensors)
  - a human-readable note explaining the fallback, surfaced back to the
    frontend so the UI can show a "estimated" badge instead of pretending
    every value came from a live sensor.
"""

import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
MEDIANS_PATH = os.path.join(HERE, "..", "models", "metrik_medians.json")

# Loaded once at import time; train_model.py must have run first.
try:
    with open(MEDIANS_PATH) as f:
        TRAINING_MEDIANS = json.load(f)
except FileNotFoundError:
    # Sensible defaults so the API can still boot before training runs.
    TRAINING_MEDIANS = {
        "Air temperature [K]": 300.1,
        "Process temperature [K]": 310.1,
        "Spindle Speed [rpm]": 1503.0,
        "Spindle Torque [Nm]": 40.1,
        "Cumulative Tool Runtime [min]": 108.0,
        "Material Hardness Index": 2.0,
        "Type_encoded": 1.0,
        "Wear x Load": 4331.0,
        "Temp Diff [K]": 10.0,
        "Est Power [W]": 6300.0,
    }

SENSOR_CONFIG = {
    "Air temperature [K]": {
        "json_key": "air_temperature",
        "required": False,
        "fallback": "median",
        "note": "Ambient shop-floor temperature. Falls back to the training "
                "median (300.1K) when no ambient probe is present.",
    },
    "Process temperature [K]": {
        "json_key": "process_temperature",
        "required": False,
        "fallback": "median",
        "note": "Spindle/coolant process temperature. Falls back to the "
                "training median when unavailable.",
    },
    "Spindle Speed [rpm]": {
        "json_key": "spindle_speed",
        "required": True,
        "fallback": "median",
        "note": "Core wear driver - required, but degrades to median rather "
                "than crashing if a sensor drops out mid-cycle.",
    },
    "Spindle Torque [Nm]": {
        "json_key": "spindle_torque",
        "required": False,
        "fallback": "derive",
        "note": "If a Feed Rate / torque sensor is missing, estimate load "
                "impact from Spindle Speed and Cumulative Tool Runtime instead.",
    },
    "Cumulative Tool Runtime [min]": {
        "json_key": "tool_runtime",
        "required": True,
        "fallback": "median",
        "note": "Tracked internally per machine; required for accurate "
                "estimated-time-to-failure calculations.",
    },
}


def _derive_spindle_torque(payload: dict) -> float:
    """
    Fallback estimate for Spindle Torque [Nm] when no torque/feed sensor exists.
    Approximates mechanical load using Spindle Speed and Cumulative Tool
    Runtime: as tools wear, more torque is typically needed to hold the
    same cut, and higher spindle speeds on a dull tool draw more load.
    This is a lightweight heuristic, not a replacement for a real sensor -
    it exists purely so the app keeps functioning end to end.
    """
    spindle = payload.get("spindle_speed", TRAINING_MEDIANS["Spindle Speed [rpm]"])
    runtime = payload.get("tool_runtime", TRAINING_MEDIANS["Cumulative Tool Runtime [min]"])
    base = TRAINING_MEDIANS["Spindle Torque [Nm]"]
    wear_adjustment = (runtime / 200.0) * 4.0       # more runtime -> more load
    speed_adjustment = (spindle - 1500) / 500.0 * 2.0  # higher rpm -> more load
    return round(max(base + wear_adjustment + speed_adjustment, 1.0), 2)


def resolve_features(payload: dict) -> dict:
    """
    Given a raw incoming sensor JSON payload (which may be missing keys),
    return a complete feature dict safe to hand to the scaler/model, plus
    metadata about which fields were estimated (so the UI can be honest
    about it) instead of silently pretending everything is a live reading.

    Returns:
        {
          "features": {<model column name>: <value>, ...},
          "estimated_fields": [<model column name>, ...],
        }
    """
    features = {}
    estimated_fields = []

    for column, config in SENSOR_CONFIG.items():
        key = config["json_key"]
        if key in payload and payload[key] is not None:
            features[column] = float(payload[key])
            continue

        # Missing -> apply the configured fallback strategy
        estimated_fields.append(column)
        if config["fallback"] == "derive" and column == "Spindle Torque [Nm]":
            features[column] = _derive_spindle_torque(payload)
        else:
            features[column] = TRAINING_MEDIANS.get(column, 0.0)

    # Material Hardness Index + Type are derived from the machine's material
    # type ('L' / 'M' / 'H'), always provided by the frontend with a safe
    # default of 'M' (medium) if somehow omitted.
    hardness_map = {"L": 1, "M": 2, "H": 3}
    material_type = payload.get("material_type", "M")
    if material_type not in hardness_map:
        material_type = "M"
        estimated_fields.append("Material Hardness Index")

    features["Material Hardness Index"] = hardness_map[material_type]
    # Type_encoded mirrors the LabelEncoder fit order from training (H=0, L=1, M=2
    # alphabetically) - main.py loads the real encoder so this is just a safe
    # default used only if the encoder object is ever unavailable.
    type_order = {"H": 0, "L": 1, "M": 2}
    features["Type_encoded"] = type_order[material_type]

    # Derived (physics) features - pure arithmetic on the fields already
    # resolved above, computed identically to models/train_model.py so the
    # live feature vector always matches what the model was trained on.
    features["Wear x Load"] = features["Cumulative Tool Runtime [min]"] * features["Spindle Torque [Nm]"]
    features["Temp Diff [K]"] = features["Process temperature [K]"] - features["Air temperature [K]"]
    features["Est Power [W]"] = features["Spindle Torque [Nm]"] * features["Spindle Speed [rpm]"] * (2 * math.pi / 60)

    return {"features": features, "estimated_fields": estimated_fields}
