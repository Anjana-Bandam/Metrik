"""
tool_physics.py
---------------
Taylor tool-life model. This is the real machining-engineering standard
(F. W. Taylor, 1907) and it is what grounds Metrik's remaining-life
estimate in physics instead of a made-up curve.

    V * T^n = C

    V = cutting speed (m/min)
    T = tool life (min)
    n = tool-material exponent (carbide ~0.25, HSS ~0.125)
    C = constant for the work material / tool pair

We use it to compute a BASELINE expected tool life for the current
cutting conditions, then blend that with the ML wear probability to get
the number we actually show the operator.
"""

import math

# n and C by tool material. Carbide is the default for CNC milling.
TOOL_CONSTANTS = {
    "carbide": {"n": 0.25, "C": 250.0},
    "hss":     {"n": 0.125, "C": 70.0},
    "ceramic": {"n": 0.35, "C": 400.0},
}

# Work-material hardness multipliers, keyed to the dataset's L/M/H Type.
# Harder stock cuts tool life down.
MATERIAL_FACTOR = {"L": 1.25, "M": 1.0, "H": 0.68}

# Typical end-mill diameter (mm) used to convert spindle RPM -> surface speed.
DEFAULT_TOOL_DIAMETER_MM = 12.0


def cutting_speed(spindle_rpm: float, diameter_mm: float = DEFAULT_TOOL_DIAMETER_MM) -> float:
    """Surface cutting speed V in m/min:  V = pi * D * N / 1000"""
    return (math.pi * diameter_mm * spindle_rpm) / 1000.0


def taylor_tool_life(spindle_rpm: float,
                     material_type: str = "M",
                     tool_material: str = "carbide",
                     depth_of_cut: float = 1.0,
                     spindle_torque: float = 40.0,
                     diameter_mm: float = DEFAULT_TOOL_DIAMETER_MM) -> float:
    """
    Expected total tool life in minutes at these cutting conditions.

    Base Taylor life is adjusted for work-material hardness, depth of cut
    and mechanical load (feed/torque), since the classic equation only
    accounts for cutting speed.
    """
    const = TOOL_CONSTANTS.get(tool_material, TOOL_CONSTANTS["carbide"])
    n, C = const["n"], const["C"]

    V = max(cutting_speed(spindle_rpm, diameter_mm), 1.0)

    # T = (C / V) ^ (1/n)
    base_life = (C / V) ** (1.0 / n)

    # Correction factors -------------------------------------------------
    life = base_life * MATERIAL_FACTOR.get(material_type, 1.0)

    # Deeper cuts remove more material per pass -> shorter life
    life *= (1.0 / max(depth_of_cut, 0.2)) ** 0.25

    # Higher mechanical load (torque proxy) -> shorter life
    life *= (40.0 / max(spindle_torque, 5.0)) ** 0.30

    # Clamp to a sane shop-floor window
    return float(min(max(life, 15.0), 600.0))


def remaining_life_minutes(elapsed_runtime: float,
                           ml_risk_pct: float,
                           spindle_rpm: float,
                           material_type: str = "M",
                           tool_material: str = "carbide",
                           depth_of_cut: float = 1.0,
                           spindle_torque: float = 40.0) -> dict:
    """
    Blend the physics baseline with the ML wear probability.

    Physics says how long this tool *should* last at these conditions.
    The ML model says how abnormal the current signature looks. When the
    model sees elevated risk we shorten the physics estimate accordingly.

    Returns remaining minutes plus a confidence band, because the problem
    statement requires us to show uncertainty rather than a single number.
    """
    expected_life = taylor_tool_life(
        spindle_rpm, material_type, tool_material, depth_of_cut, spindle_torque
    )

    physics_remaining = max(expected_life - elapsed_runtime, 0.0)

    # ML derating: at 0% risk trust physics fully; at 100% risk collapse it.
    derate = 1.0 - (ml_risk_pct / 100.0) ** 1.5
    blended = physics_remaining * max(derate, 0.02)

    # Confidence band widens as risk rises (we are less certain near failure)
    spread = 0.18 + (ml_risk_pct / 100.0) * 0.22
    low = max(blended * (1 - spread), 0.0)
    high = blended * (1 + spread)

    return {
        "expected_tool_life_min": round(expected_life, 1),
        "remaining_min": round(blended, 1),
        "remaining_low_min": round(low, 1),
        "remaining_high_min": round(high, 1),
        "cutting_speed_m_min": round(cutting_speed(spindle_rpm), 1),
        "life_consumed_pct": round(
            min(elapsed_runtime / max(expected_life, 1) * 100, 100), 1
        ),
    }


def recommended_feed_override(risk_pct: float) -> dict:
    """
    Translate risk into the physical action an operator can actually take:
    turning the feed override dial on the CNC control panel.

    Never recommends increasing feed, and never drops below 70% (below that
    you risk rubbing/work-hardening instead of cutting, which is unsafe).
    """
    if risk_pct >= 85:
        return {"override_pct": 100, "action": "change_tool",
                "text": "Change the tool at the next safe stop. Reducing feed will not recover this."}
    if risk_pct >= 70:
        return {"override_pct": 85, "action": "reduce_feed",
                "text": "Set feed override to 85% and plan a tool change this shift."}
    if risk_pct >= 40:
        return {"override_pct": 90, "action": "reduce_feed",
                "text": "Set feed override to 90% to extend life to the next scheduled break."}
    return {"override_pct": 100, "action": "continue",
            "text": "No override needed. Continue at programmed feed."}

def physics_wear_risk(life_consumed_pct: float) -> float:
    """
    Convert 'how much of the expected tool life is used up' into a risk
    percentage.

    Cubic rather than linear, because tool wear is not linear in time: a tool
    at 50% of expected life is in good shape, but risk climbs steeply through
    the last quarter. This is the signal the ML model structurally cannot
    provide - a worn tool often still cuts with a perfectly normal spindle
    signature right up until it fails.

        50% consumed -> ~13% risk
        80% consumed -> ~51% risk
        90% consumed -> ~73% risk
        98% consumed -> ~94% risk
    """
    r = min(max(life_consumed_pct, 0.0), 100.0) / 100.0
    return round((r ** 3) * 100, 1)