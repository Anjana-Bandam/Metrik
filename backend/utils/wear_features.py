"""
wear_features.py
------------------
Metrik | Flank-wear feature extraction (shared by training and inference)

This module is the single source of truth for how raw condition-monitoring
signals become model features. `models/train_wear_model.py` uses it offline
and `api/main.py` uses it online, so a live machine can never drift out of
sync with how the model was trained - the classic cause of a model that
scores well in a paper and behaves badly on the shop floor.

Signals
--------
Seven channels, matching an ordinary CNC condition-monitoring package:
a 3-axis cutting-force dynamometer, a 3-axis accelerometer, and an
acoustic-emission sensor. These are the channels recorded in the PHM 2010
milling challenge, which is what the wear model is trained on.

Why signals are expressed RELATIVE to a fresh tool
---------------------------------------------------
Absolute force and vibration levels depend on the fixture, the workpiece
batch and the machine itself, so they differ between one tool and the next
even at identical wear. A model trained on absolute levels therefore learns
the setup, not the wear, and collapses when it meets a new tool.

Metrik instead records a short baseline in the first ~30 seconds after every
tool change and feeds the model each channel's ratio and delta against that
baseline. This is exactly what an experienced machinist does by ear - judging
how much *louder and harder* a cut has become than it was when the insert was
new.

On its own, baseline normalisation is roughly neutral in the measured
leave-one-tool-out ablation (see train_wear_model.py section 2); the large
gain - MAE 20.0 um -> 16.0 um - comes from the cumulative-exposure and
smoothed-trend features that sit on top of it. It is kept because it is what
makes those cumulative features comparable between one machine and the next,
and because it is what allows the model to be deployed on a machine whose
absolute force levels were never in the training set at all.
"""

import numpy as np

try:                                   # scipy is only needed for the shape stats
    from scipy import stats as _sps
    _HAVE_SCIPY = True
except ImportError:                    # pragma: no cover - graceful degradation
    _HAVE_SCIPY = False

# ---------------------------------------------------------------------------
# Contract shared with train_wear_model.py - changing any of these means the
# saved model must be retrained.
# ---------------------------------------------------------------------------
SIGNALS = [
    "force_x", "force_y", "force_z",
    "vibration_x", "vibration_y", "vibration_z",
    "acoustic_emission_rms",
]

WINDOW_SECONDS = 2.0        # one feature row per 2 s of cutting
BASELINE_WINDOWS = 15       # ~30 s of fresh-tool cutting defines the baseline
EWM_SPAN = 25               # smoothing span for the trend features

# Per-channel statistics computed inside one window.
_STATS = ["rms", "std", "p2p", "mean", "kurt", "skew"]

# ISO 8688 tool-life criterion for milling: an insert is considered worn out
# at 0.3 mm of flank wear. Metrik reports wear as a percentage of this.
ISO_WEAR_LIMIT_MM = 0.30


def window_stats(samples: dict) -> dict:
    """
    Reduce one window of raw samples to per-channel statistics.

    `samples` maps each channel name in SIGNALS to a sequence of raw readings
    captured over WINDOW_SECONDS. Channels that are absent are reported as
    zeros so a machine with a partial sensor package still produces a complete,
    correctly-ordered feature row (see the same philosophy in sensor_config.py).
    """
    out = {}
    for s in SIGNALS:
        v = np.asarray(samples.get(s, []), dtype=float)
        if v.size == 0:
            for stat in _STATS:
                out[f"{s}_{stat}"] = 0.0
            continue
        out[f"{s}_rms"] = float(np.sqrt((v ** 2).mean()))
        out[f"{s}_std"] = float(v.std())
        out[f"{s}_p2p"] = float(v.max() - v.min())
        out[f"{s}_mean"] = float(v.mean())
        if _HAVE_SCIPY and v.std() > 1e-12:
            out[f"{s}_kurt"] = float(_sps.kurtosis(v))
            out[f"{s}_skew"] = float(_sps.skew(v))
        else:
            out[f"{s}_kurt"] = 0.0
            out[f"{s}_skew"] = 0.0
    return out


def raw_stat_columns() -> list:
    """Column names produced by window_stats(), in a fixed order."""
    return [f"{s}_{stat}" for s in SIGNALS for stat in _STATS]


def relative_columns() -> list:
    return [f"{c}__rel" for c in raw_stat_columns()]


def delta_columns() -> list:
    return [f"{c}__dlt" for c in raw_stat_columns()]


CUMULATIVE_COLUMNS = ["cum_force_energy", "force_rms_ewm", "vib_rms_ewm"]


def feature_columns() -> list:
    """
    The exact, ordered feature vector the wear model consumes.
    train_wear_model.py trains on this order; main.py predicts on it.
    """
    return (relative_columns()
            + delta_columns()
            + CUMULATIVE_COLUMNS
            + ["cut_time_s"])


def apply_baseline(stats: dict, baseline: dict) -> dict:
    """
    Express one window's statistics relative to this tool's fresh-tool
    baseline: a ratio (how many times harder the cut has become) and a delta
    (how much more, in raw units). Both are useful - the ratio transfers
    across machines, the delta preserves absolute severity.
    """
    out = {}
    for c in raw_stat_columns():
        now = float(stats.get(c, 0.0))
        base = float(baseline.get(c, 0.0))
        out[f"{c}__rel"] = now / base if abs(base) > 1e-9 else 0.0
        out[f"{c}__dlt"] = now - base
    return out


def force_energy(stats: dict) -> float:
    """
    Instantaneous mechanical exposure - the squared magnitude of the cutting
    force vector. Accumulated over a tool's life this approximates the total
    mechanical work the edge has absorbed, which is what physically drives
    abrasive flank wear.
    """
    return float(stats.get("force_x_rms", 0.0) ** 2
                 + stats.get("force_y_rms", 0.0) ** 2
                 + stats.get("force_z_rms", 0.0) ** 2)


def build_feature_row(stats: dict, baseline: dict, cum_energy: float,
                      force_ewm: float, vib_ewm: float, cut_time_s: float) -> list:
    """
    Assemble the final ordered feature vector for one window.

    The caller owns the running state (`cum_energy`, `force_ewm`, `vib_ewm`)
    because it is per-tool and must survive between calls; see
    Machine.observe_wear_window() in utils/machine_state.py.
    """
    row = apply_baseline(stats, baseline)
    row["cum_force_energy"] = float(cum_energy)
    row["force_rms_ewm"] = float(force_ewm)
    row["vib_rms_ewm"] = float(vib_ewm)
    row["cut_time_s"] = float(cut_time_s)
    return [row[c] for c in feature_columns()]


def ewm_update(previous: float, value: float, span: int = EWM_SPAN) -> float:
    """Causal exponential moving average - matches pandas' ewm(span=...)."""
    alpha = 2.0 / (span + 1.0)
    if previous is None:
        return float(value)
    return float(alpha * value + (1.0 - alpha) * previous)


# Practical change-out point in TRUE wear. ISO 8688 calls the insert finished
# at 0.30 mm; shops change before that so the criterion is never crossed
# part-way through a component. 0.225 mm (75%) is the usual practical point.
TRUE_CHANGE_POINT_MM = 0.225

# ---------------------------------------------------------------------------
# Alert thresholds, expressed on the model's OWN PREDICTED scale.
#
# These deliberately sit below TRUE_CHANGE_POINT_MM, and that is not a fudge.
# Under leave-one-tool-out the regressor systematically under-reads at the worn
# extreme - measured shortfall 34-45 um on the held-out cutters - because with
# only three cutters, every held-out tool ends its life at a wear level neither
# training tool ever reached, and a tree model cannot extrapolate past its
# training range. Calibration was tried and rejected: linear and isotonic maps
# both made MAE worse (16.0 -> 19.6 / 19.9 um) without lifting the ceiling.
#
# So the honest engineering answer is to set the decision threshold where the
# model actually separates worn from unworn, rather than where we wish it did.
# Validated by nested leave-one-tool-out against ground truth "genuinely past
# 0.225 mm":
#
#     predicted >= 0.165 mm  ->  precision 0.227, recall 1.000  (0 worn tools missed)
#     predicted >= 0.170 mm  ->  precision 0.271, recall 0.915  (6 missed)
#     predicted >= 0.225 mm  ->  never fires at all
#
# 0.165 is chosen over the marginally higher-F1 0.178 on purpose: for a tool
# change, a miss costs scrapped parts while a false alarm costs changing an
# insert slightly early. Recall is worth more than precision here, and 0.165 is
# the loosest threshold that misses nothing. A machine flagged at 0.165 is
# typically around 0.18 mm of true wear - genuinely near the end of its life,
# so the "false" alarms are early rather than wrong.
#
# Retraining on more cutters should raise these toward the true scale; they are
# saved into metrik_wear_meta.json by train_wear_model.py so the API always
# uses the values that were actually validated against the shipped model.
# ---------------------------------------------------------------------------
WEAR_WATCH_MM = 0.130
WEAR_ACT_MM = 0.165


def wear_status(wear_mm: float,
                watch_mm: float = WEAR_WATCH_MM,
                act_mm: float = WEAR_ACT_MM) -> str:
    """Traffic light for a predicted flank-wear value, in millimetres."""
    if wear_mm < watch_mm:
        return "green"
    if wear_mm < act_mm:
        return "yellow"
    return "red"


# Minimum history before a remaining-life figure is worth quoting. Below this
# the wear trend is dominated by prediction noise and the projection swings
# wildly between readings, which is worse than showing nothing.
RUL_MIN_POINTS = 8
RUL_WINDOW = 20          # fit the trend on at most this many recent readings


def estimate_rul(runtimes, wears, target_mm: float = WEAR_ACT_MM):
    """
    Remaining useful life: how much longer until this tool reaches the
    change-out point, in the same time unit as `runtimes`.

    Rather than assuming a wear law, this fits the tool's OWN recent wear trend
    by least squares and projects it forward. Real inserts differ enough from
    one another - and from any textbook curve - that the tool's own recent
    behaviour is the better predictor, and it also means the estimate adapts
    when a job changes.

    Wear accelerates near end of life, so a straight-line fit is slightly
    optimistic; the returned interval is deliberately asymmetric to lean early
    rather than late, because being told to change a tool sooner than needed is
    cheaper than being told too late.

    Returns None when there is not enough history or the tool is not measurably
    wearing yet - callers must render that as "not enough data", never as zero.
    """
    n = min(len(runtimes), len(wears))
    if n < RUL_MIN_POINTS:
        return None

    t = np.asarray(runtimes[-RUL_WINDOW:], dtype=float)
    w = np.asarray(wears[-RUL_WINDOW:], dtype=float)
    if t.size < RUL_MIN_POINTS or (t.max() - t.min()) <= 0:
        return None

    current = float(w[-1])
    if current >= target_mm:
        return {"rul": 0.0, "low": 0.0, "high": 0.0,
                "rate_per_unit": 0.0, "current_mm": current, "at_limit": True}

    # Least-squares slope = wear rate.
    slope, intercept = np.polyfit(t, w, 1)
    if slope <= 1e-9:
        return None                       # flat or falling: no usable trend

    # Spread from the slope's standard error, so a noisy trend widens the range
    # instead of quietly pretending to precision it does not have.
    resid = w - (slope * t + intercept)
    dof = max(t.size - 2, 1)
    denom = float(((t - t.mean()) ** 2).sum()) or 1e-9
    slope_se = float(np.sqrt((resid ** 2).sum() / dof / denom))

    # Refuse to project from a trend that is not distinguishable from flat.
    # Early in a tool's life the wear curve is almost level, and dividing by a
    # slope that is mostly noise produces confident-looking nonsense - measured
    # on the PHM cutters, this one guard is the difference between a median RUL
    # error of ~9 minutes and a *mean* error of over two hours, because a
    # handful of near-zero slopes dominate everything else.
    if slope <= 2.0 * slope_se:
        return None

    remaining = (target_mm - current) / slope

    # Nor project far beyond the evidence: a tool that has run 10 minutes
    # cannot credibly be told it has 6 hours left. Cap at 3x elapsed cutting
    # time and report the cap honestly rather than inventing precision.
    elapsed = float(t[-1] - t[0]) if t.size > 1 else 0.0
    horizon = max(elapsed * 3.0, 1e-9)
    capped = remaining > horizon
    remaining = min(remaining, horizon)

    hi_rate = slope + 1.96 * slope_se          # wearing faster -> less time left
    lo_rate = max(slope - 1.96 * slope_se, 1e-9)
    low = (target_mm - current) / hi_rate if hi_rate > 0 else remaining
    high = (target_mm - current) / lo_rate

    # Cap the optimistic end at 3x the point estimate: with a nearly flat fit
    # the upper bound diverges, and "12 000 minutes left" is not information.
    high = min(high, remaining * 3.0)

    return {
        "rul": float(max(remaining, 0.0)),
        "low": float(max(min(low, remaining), 0.0)),
        "high": float(max(min(high, horizon), remaining)),
        "rate_per_unit": float(slope),
        "current_mm": current,
        "at_limit": False,
        "capped": bool(capped),
    }
