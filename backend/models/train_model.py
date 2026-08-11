"""
train_model.py
----------------
Metrik | AI-Powered CNC Predictive Maintenance

Loads the Kaggle "Machine Predictive Maintenance Classification" dataset,
renames its columns to real-world CNC terminology, engineers the
Material Hardness Index feature, trains an XGBoost classifier that
outputs a *probability* of tool wear (never a hard 0/1), and persists
every artifact (model, scaler, label encoder, and training medians)
that main.py needs at inference time.

Run this once before starting the API:
    python backend/models/train_model.py
"""

import os
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier
from sklearn.metrics import roc_auc_score, classification_report

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(HERE, "..", "data", "predictive_maintenance.csv")
ARTIFACT_DIR = HERE  # .pkl files live alongside this script

MODEL_PATH = os.path.join(ARTIFACT_DIR, "metrik_xgb_model.pkl")
SCALER_PATH = os.path.join(ARTIFACT_DIR, "metrik_scaler.pkl")
ENCODER_PATH = os.path.join(ARTIFACT_DIR, "metrik_type_encoder.pkl")
MEDIANS_PATH = os.path.join(ARTIFACT_DIR, "metrik_medians.json")

# ---------------------------------------------------------------------------
# 1. Load raw Kaggle dataset
# ---------------------------------------------------------------------------
print("[Metrik] Loading raw dataset...")
df = pd.read_csv(DATA_PATH)

# ---------------------------------------------------------------------------
# 2. Rename columns to real-world CNC terminology (crucial per spec)
# ---------------------------------------------------------------------------
df = df.rename(columns={
    "Rotational speed [rpm]": "Spindle Speed [rpm]",
    "Torque [Nm]": "Feed Rate [Nm]",          # Torque used as a proxy for mechanical load/feed
    "Tool wear [min]": "Cumulative Tool Runtime [min]",
})

# ---------------------------------------------------------------------------
# 3. Feature engineering: Material Hardness Index from the 'Type' column
#    L (Low) = 1, M (Medium) = 2, H (High) = 3
# ---------------------------------------------------------------------------
HARDNESS_MAP = {"L": 1, "M": 2, "H": 3}
df["Material Hardness Index"] = df["Type"].map(HARDNESS_MAP)

# Encode 'Type' for the model itself (kept separately from the hardness index
# so the model sees both the categorical identity and the ordinal hardness)
type_encoder = LabelEncoder()
df["Type_encoded"] = type_encoder.fit_transform(df["Type"])

# ---------------------------------------------------------------------------
# 4. Feature set. These are exactly the fields the FastAPI backend will
#    expect in incoming sensor JSON (see utils/sensor_config.py).
# ---------------------------------------------------------------------------
FEATURE_COLUMNS = [
    "Air temperature [K]",
    "Process temperature [K]",
    "Spindle Speed [rpm]",
    "Feed Rate [Nm]",
    "Cumulative Tool Runtime [min]",
    "Material Hardness Index",
    "Type_encoded",
]
TARGET_COLUMN = "Target"

X = df[FEATURE_COLUMNS].copy()
y = df[TARGET_COLUMN].copy()

# ---------------------------------------------------------------------------
# 5. Save training medians -> used by the backend's "sensor flexibility"
#    fallback logic when a live machine is missing a sensor reading.
# ---------------------------------------------------------------------------
medians = X.median(numeric_only=True).to_dict()
with open(MEDIANS_PATH, "w") as f:
    json.dump(medians, f, indent=2)
print(f"[Metrik] Saved training medians -> {MEDIANS_PATH}")

# ---------------------------------------------------------------------------
# 6. Train / test split
# ---------------------------------------------------------------------------
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

# ---------------------------------------------------------------------------
# 7. Scale numeric data (StandardScaler) - fit on train only
# ---------------------------------------------------------------------------
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

# ---------------------------------------------------------------------------
# 8. Train XGBoost classifier
#    The dataset is heavily imbalanced (~3.4% positive), so scale_pos_weight
#    is used to keep the model from just predicting "Normal" every time.
# ---------------------------------------------------------------------------
pos = y_train.sum()
neg = len(y_train) - pos
scale_pos_weight = neg / max(pos, 1)

print(f"[Metrik] Training XGBoost | positives={pos} negatives={neg} "
      f"scale_pos_weight={scale_pos_weight:.2f}")

model = XGBClassifier(
    n_estimators=300,
    max_depth=5,
    learning_rate=0.05,
    subsample=0.85,
    colsample_bytree=0.85,
    scale_pos_weight=scale_pos_weight,
    eval_metric="auc",
    random_state=42,
    n_jobs=-1,
)
model.fit(X_train_scaled, y_train)

# ---------------------------------------------------------------------------
# 9. Evaluate
# ---------------------------------------------------------------------------
proba = model.predict_proba(X_test_scaled)[:, 1]
auc = roc_auc_score(y_test, proba)
print(f"[Metrik] Test ROC-AUC: {auc:.4f}")
print(classification_report(y_test, (proba >= 0.5).astype(int)))

# ---------------------------------------------------------------------------
# 10. Persist artifacts
# ---------------------------------------------------------------------------
joblib.dump(model, MODEL_PATH)
joblib.dump(scaler, SCALER_PATH)
joblib.dump(type_encoder, ENCODER_PATH)

print("[Metrik] Saved artifacts:")
print(f"  - Model   -> {MODEL_PATH}")
print(f"  - Scaler  -> {SCALER_PATH}")
print(f"  - Encoder -> {ENCODER_PATH}")
print("[Metrik] Training complete. Start the API with:")
print("  uvicorn backend.api.main:app --reload --port 8000")
