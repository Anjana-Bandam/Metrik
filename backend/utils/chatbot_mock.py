"""
chatbot_mock.py
---------------
Two things live here:

  1. narrative_for_machine()  - the context paragraph shown on the card
  2. answer_question()        - a genuine Q&A assistant over live state

The assistant is intent-matched with keyword scoring and then fills the
answer from the machine's ACTUAL current values, so it is grounded rather
than generic. No API key, no network call. Swapping in Azure OpenAI later
means replacing answer_question()'s body and keeping its signature.

Every answer is decision-support framed: it recommends, it never commands,
and it never suggests an unsafe machining change.
"""

import re
from typing import List, Dict, Optional

_UNIT_STRIP = re.compile(r"\s*\[[^\]]*\]")


def _clean(feature: str) -> str:
    return _UNIT_STRIP.sub("", feature).strip().lower()


def _top_driver(shap_values: List[Dict]) -> str:
    if not shap_values:
        return "current operating parameters"
    top = max(shap_values, key=lambda d: d["contribution_pct"])
    return _clean(top["feature"])


def _fmt(minutes: float) -> str:
    minutes = int(minutes)
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h}h {m}m"
    return f"{h}h" if h else f"{m}m"


# ---------------------------------------------------------------------------
# 1. Card narrative
# ---------------------------------------------------------------------------
def narrative_for_machine(machine_name: str, risk_pct: float,
                          shap_values: List[Dict], life: dict,
                          override: dict, state: str) -> str:
    if state == "OFFLINE":
        return (f"{machine_name} is not reporting. Metrik has no live signal "
                f"from this machine, so no prediction is being made. Check the "
                f"gateway connection.")
    if state == "IDLE":
        return (f"{machine_name} is idle with no job loaded. The tool has "
                f"{_fmt(life['remaining_min'])} of estimated life left from its "
                f"last run - risk will resume updating when cutting restarts.")
    if state == "TOOL_CHANGE":
        return (f"{machine_name} is in a tool change. Log the change when the "
                f"new tool is fitted so Metrik resets cumulative runtime and "
                f"records whether the old tool was genuinely worn.")

    driver = _top_driver(shap_values)
    band = f"{_fmt(life['remaining_low_min'])}-{_fmt(life['remaining_high_min'])}"

    if risk_pct >= 70:
        return (f"{machine_name} is in the high-risk band at {risk_pct:.0f}% wear "
                f"probability, driven mainly by {driver}. Estimated remaining "
                f"life is {_fmt(life['remaining_min'])} (confidence range {band}). "
                f"{override['text']} Metrik does not stop machines - this is a "
                f"recommendation for the operator to action.")
    if risk_pct >= 40:
        return (f"{machine_name} is trending toward wear at {risk_pct:.0f}% "
                f"probability, with {driver} the leading contributor. Roughly "
                f"{_fmt(life['remaining_min'])} of tool life remains (range {band}). "
                f"{override['text']}")
    return (f"{machine_name} is running normally at {risk_pct:.0f}% wear "
            f"probability. {driver.capitalize()} is within expected range and the "
            f"tool has about {_fmt(life['remaining_min'])} of life left. "
            f"No action needed.")


def narrative_for_simulation(risk_pct: float, shap_values: List[Dict],
                             life: dict, override: dict) -> str:
    driver = _top_driver(shap_values)
    if risk_pct >= 70:
        return (f"At these settings the projected wear risk is {risk_pct:.0f}%, "
                f"driven by {driver}. Expected tool life at this cutting speed is "
                f"only {_fmt(life['expected_tool_life_min'])}. Not recommended for "
                f"an unattended long run - reduce spindle speed or depth of cut.")
    if risk_pct >= 40:
        return (f"Projected risk {risk_pct:.0f}%. {driver.capitalize()} is pushing "
                f"this up. Expected tool life at these conditions is about "
                f"{_fmt(life['expected_tool_life_min'])}. Workable, but plan a tool "
                f"change within the shift.")
    return (f"Projected risk is low at {risk_pct:.0f}%. Expected tool life at these "
            f"conditions is around {_fmt(life['expected_tool_life_min'])}. These "
            f"settings are suitable for an extended run.")


# ---------------------------------------------------------------------------
# 2. Q&A assistant
# ---------------------------------------------------------------------------
INTENTS = {
    "why_risk":      ["why", "reason", "cause", "driving", "driver", "what is causing", "explain"],
    "what_do":       ["what should", "what do i do", "action", "recommend", "next step", "should i", "advice"],
    "when_change":   ["when", "how long", "time left", "remaining", "life left", "change the tool", "replace"],
    "cost":          ["cost", "money", "scrap", "dollar", "loss", "expensive", "savings"],
    "explain_shap":  ["shap", "feature importance", "how does the model", "contribution", "explainab"],
    "explain_model": ["model", "algorithm", "xgboost", "trained", "accuracy", "how accurate", "confidence"],
    "safety":        ["safe", "stop the machine", "shut down", "shutdown", "auto", "will it stop"],
    "connection":    ["opc", "mtconnect", "connect", "data come from", "sensor", "integration", "focas"],
    "tool_life":     ["taylor", "physics", "tool life", "cutting speed", "formula", "equation"],
    "compare":       ["worst", "which machine", "highest risk", "compare", "most at risk", "priority"],
    "greeting":      ["hi", "hello", "hey", "help", "what can you do"],
}


def _detect_intent(q: str) -> str:
    ql = q.lower()
    best, best_score = "fallback", 0
    for intent, phrases in INTENTS.items():
        score = sum(len(p) for p in phrases if p in ql)
        if score > best_score:
            best, best_score = intent, score
    return best


def answer_question(question: str, machine: Optional[dict] = None,
                    fleet: Optional[List[dict]] = None) -> str:
    """
    machine: the currently open machine snapshot (may be None on the
             dashboard-level chat)
    fleet:   all machine snapshots, for cross-machine questions
    """
    intent = _detect_intent(question)
    fleet = fleet or []

    # --- questions that do not need a specific machine ---------------------
    if intent == "greeting":
        return ("I'm the Metrik assistant. I can explain why a machine is at "
                "risk, what the SHAP drivers mean, when to change a tool, what "
                "the scrap cost exposure is, and how Metrik connects to your "
                "machines. Ask me anything about what's on screen.")

    if intent == "safety":
        return ("Metrik never stops, starts or reconfigures a machine. It is "
                "decision support only - it surfaces a probability with a "
                "confidence range and a recommended feed override, and a person "
                "on the floor decides what to do. Nothing it outputs is wired to "
                "a machine control.")

    if intent == "connection":
        return ("Metrik reads live data through a connector layer rather than one "
                "fixed protocol. Adapters exist for OPC UA (including the umati "
                "companion spec for machine tools), MTConnect, FANUC FOCAS, and a "
                "retrofit gateway using a spindle current clamp or vibration "
                "sensor for older machines with no digital port. Machines with no "
                "connectivity at all can be brought in via CSV upload. Each card "
                "shows which channel it is using.")

    if intent == "explain_shap":
        return ("SHAP assigns each input parameter a share of the responsibility "
                "for one specific prediction. The bar chart shows those shares "
                "normalised to 100%, so if spindle speed reads 60% it contributed "
                "roughly three times as much to that risk score as a parameter at "
                "20%. Amber bars push risk up, teal bars pull it down. It is "
                "per-prediction, not a global ranking, which is why the chart "
                "changes as conditions change.")

    if intent == "explain_model":
        return ("The risk score comes from an XGBoost classifier trained on "
                "machining parameters and runtime, with class weighting to correct "
                "for the low failure rate in the training data. It outputs a "
                "probability, never a hard yes/no. That probability is then blended "
                "with a Taylor tool-life physics estimate to produce the remaining "
                "life figure and its confidence range. Treat the range as the "
                "honest answer and the midpoint as a planning number.")

    if intent == "tool_life":
        return ("Remaining life is not guessed from the risk score alone. Metrik "
                "computes an expected tool life from Taylor's tool life equation, "
                "V x T^n = C, where V is surface cutting speed derived from spindle "
                "RPM and tool diameter. That baseline is corrected for work-material "
                "hardness, depth of cut and mechanical load, then derated by the ML "
                "risk score. So the number reflects both the physics of the cut and "
                "what the live signature looks like.")

    if intent == "compare" and fleet:
        active = [m for m in fleet if m["state"] == "RUNNING"]
        if not active:
            return "No machines are currently running, so there is nothing to rank."
        ranked = sorted(active, key=lambda m: m["risk_pct"], reverse=True)
        top = ranked[0]
        rest = ", ".join(f"{m['name']} at {m['risk_pct']:.0f}%" for m in ranked[1:4])
        return (f"{top['name']} needs attention first at {top['risk_pct']:.0f}% wear "
                f"probability, with about {top['est_time_to_failure']} of tool life "
                f"left. After that: {rest}." if rest else
                f"{top['name']} is the only running machine, at {top['risk_pct']:.0f}%.")

    # --- machine-specific -------------------------------------------------
    if machine is None:
        return ("Open a machine to ask about it specifically, or ask me about "
                "how the model works, how Metrik connects to machines, or which "
                "machine needs attention first.")

    name = machine["name"]
    risk = machine["risk_pct"]
    state = machine["state"]

    if state == "OFFLINE":
        return (f"{name} is offline and not reporting, so there is no current "
                f"prediction. The last known reading was at "
                f"{machine.get('last_seen', 'an unknown time')}. Check the gateway.")

    if intent == "why_risk":
        drivers = machine["shap_values"][:3]
        parts = [f"{_clean(d['feature'])} ({d['contribution_pct']:.0f}%, "
                 f"{d['direction']})" for d in drivers]
        return (f"{name} is at {risk:.0f}% wear probability. The three largest "
                f"contributors to this specific prediction are " +
                ", ".join(parts) + ". The tool has run "
                f"{machine['sensors']['tool_runtime']:.0f} minutes against an "
                f"expected life of {machine['life']['expected_tool_life_min']:.0f} "
                f"minutes at the current cutting speed.")

    if intent == "what_do":
        ov = machine["override"]
        return (f"{ov['text']} For context, {name} is at {risk:.0f}% risk with "
                f"{machine['est_time_to_failure']} of estimated life left. If you "
                f"do change the tool, log it in Metrik so runtime resets and the "
                f"model learns whether this prediction was correct.")

    if intent == "when_change":
        life = machine["life"]
        return (f"{name} has an estimated {_fmt(life['remaining_min'])} of tool "
                f"life remaining, with a confidence range of "
                f"{_fmt(life['remaining_low_min'])} to {_fmt(life['remaining_high_min'])}. "
                f"It has consumed about {life['life_consumed_pct']:.0f}% of expected "
                f"life. Plan the change toward the lower end of that range rather "
                f"than the midpoint if the part is high-value.")

    if intent == "cost":
        return (f"At {risk:.0f}% wear probability the scrap-cost exposure on "
                f"{name} is approximately ${machine['cost_impact']:.0f} - that is "
                f"the expected value of parts likely to go dimensionally out of "
                f"tolerance before the tool is changed. A planned tool change "
                f"costs a few minutes of spindle time; an unplanned one costs the "
                f"part, the rework and the downtime.")

    # fallback
    return (f"I can tell you why {name} is at {risk:.0f}%, what to do about it, "
            f"when to change the tool, or what the cost exposure is. I can also "
            f"explain how the model and the SHAP chart work. Which would help?")