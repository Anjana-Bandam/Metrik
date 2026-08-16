"""
chatbot_mock.py
---------------
Two things live here:

  1. narrative_for_machine() / narrative_for_simulation() - the context
     paragraph shown on the card and in the simulator. Deterministic,
     rule-based, no network call - unchanged from the original design.

  2. answer_question() - the chat assistant. It now calls a real LLM
     (see _answer_with_llm) so it can hold an open-ended conversation
     instead of only matching one of a fixed list of intents. Every call
     is grounded in the caller's actual live machine/fleet data via the
     system prompt, so answers stay factual rather than generic - the
     model is told what's on screen, not left to guess.

     Backed by Groq's free-tier API (a Llama model, not Anthropic) so the
     chatbot costs nothing to run - see console.groq.com/keys for a free
     key. Requires GROQ_API_KEY in the backend's environment. If it's
     not set, or the call fails for any reason (network, rate limit, bad
     key), answer_question() falls back to the original keyword-matched
     responder below - the chat feature degrades gracefully instead of
     breaking.

Every answer is decision-support framed: it recommends, it never commands,
and it never suggests an unsafe machining change.
"""

import os
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
# Fallback bands, used only if a caller doesn't pass the live calibrated
# values. main.py always passes RISK_WATCH/RISK_ALERT explicitly - these
# constants exist so this module still works in isolation (e.g. tests).
DEFAULT_WATCH_PCT = 15.6
DEFAULT_ALERT_PCT = 27.7


def narrative_for_machine(machine_name: str, risk_pct: float,
                          shap_values: List[Dict], life: dict,
                          override: dict, state: str,
                          watch_pct: float = DEFAULT_WATCH_PCT,
                          alert_pct: float = DEFAULT_ALERT_PCT) -> str:
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

    if risk_pct >= alert_pct:
        return (f"{machine_name} is in the high-risk band at {risk_pct:.0f}% scrap "
                f"risk, driven mainly by {driver}. Estimated remaining "
                f"life is {_fmt(life['remaining_min'])} (confidence range {band}). "
                f"{override['text']} Metrik does not stop machines - this is a "
                f"recommendation for the operator to action.")
    if risk_pct >= watch_pct:
        return (f"{machine_name} is trending toward risk at {risk_pct:.0f}% "
                f"scrap probability, with {driver} the leading contributor. Roughly "
                f"{_fmt(life['remaining_min'])} of tool life remains (range {band}). "
                f"{override['text']}")
    return (f"{machine_name} is running normally at {risk_pct:.0f}% scrap "
            f"risk. {driver.capitalize()} is within expected range and the "
            f"tool has about {_fmt(life['remaining_min'])} of life left. "
            f"No action needed.")


def narrative_for_simulation(risk_pct: float, shap_values: List[Dict],
                             life: dict, override: dict,
                             watch_pct: float = DEFAULT_WATCH_PCT,
                             alert_pct: float = DEFAULT_ALERT_PCT) -> str:
    driver = _top_driver(shap_values)
    if risk_pct >= alert_pct:
        return (f"At these settings the projected scrap risk is {risk_pct:.0f}%, "
                f"driven by {driver}. Expected tool life at this cutting speed is "
                f"only {_fmt(life['expected_tool_life_min'])}. Not recommended for "
                f"an unattended long run - reduce spindle speed or depth of cut.")
    if risk_pct >= watch_pct:
        return (f"Projected scrap risk {risk_pct:.0f}%. {driver.capitalize()} is "
                f"pushing this up. Expected tool life at these conditions is about "
                f"{_fmt(life['expected_tool_life_min'])}. Workable, but plan a tool "
                f"change within the shift.")
    return (f"Projected scrap risk is low at {risk_pct:.0f}%. Expected tool life at "
            f"these conditions is around {_fmt(life['expected_tool_life_min'])}. "
            f"These settings are suitable for an extended run.")


# ---------------------------------------------------------------------------
# 2. Q&A assistant - Claude-backed, with a rule-based fallback
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are the Metrik assistant, embedded inside Metrik - an AI \
predictive-maintenance app for CNC machine shops. Metrik runs TWO separate \
models and you must never conflate their numbers:
  1. SCRAP RISK - a calibrated probability (0-100%) that the current cut ends \
     in a wear-driven scrap event, from an XGBoost classifier on live spindle \
     telemetry, explained with SHAP, blended with a physics-based (Taylor \
     tool-life equation) remaining-life estimate.
  2. MEASURED TOOL WEAR - flank wear in millimetres against the ISO 8688 0.30mm \
     limit, from a SEPARATE regression model trained on real physically \
     measured wear (not synthetic data), with a remaining-useful-life estimate \
     in minutes once a wear trend is established.
When discussing risk, be explicit about which of the two you mean - "scrap \
risk" or "measured tool wear" - never say just "risk" or "wear" ambiguously, \
and never quote one model's number as if it were the other's. It is decision \
support only: it never starts, stops, or reconfigures a machine, and every \
recommendation is for a person on the floor to act on - never state or imply \
that Metrik (or you) can control a machine directly.

You can hold an ordinary conversation, not just answer questions about the \
fleet - if the user asks something unrelated to Metrik (small talk, a general \
knowledge question, anything), just answer it naturally and helpfully like \
any capable assistant would. You don't need to redirect every off-topic \
message back to machining.

When a question is about the fleet or a specific machine, ground your answer \
in the live data given below - never invent numbers, machine names, or \
readings that aren't in it. If the data needed to answer isn't present, say \
so plainly instead of guessing.

Keep answers conversational and concise - a few sentences unless the user \
asks for more detail. Do not include internal or system XML tags in your \
response."""

try:
    from dotenv import load_dotenv
    load_dotenv()          # picks up GROQ_API_KEY from backend/.env, if present
except ImportError:
    pass

_GROQ_MODEL = "llama-3.3-70b-versatile"
_GROQ_KEY = os.environ.get("GROQ_API_KEY")

try:
    from groq import Groq
    _client = Groq(api_key=_GROQ_KEY) if _GROQ_KEY else None
except Exception:
    _client = None

if not _GROQ_KEY:
    print("[Metrik] WARNING: GROQ_API_KEY is not set. The chatbot will use "
          "the old rule-based responder instead of a real conversation. Get a "
          "free key at https://console.groq.com/keys, set it in backend/.env "
          "(see .env.example), then restart the server.")


def _machine_context(machine: Optional[dict]) -> str:
    if not machine:
        return ("No specific machine is currently open in the UI. If the "
                "question needs one, ask which machine, or answer from the "
                "fleet snapshot above.")
    if machine.get("state") == "OFFLINE":
        return (f"The machine currently open is {machine.get('name')} - it is "
                f"OFFLINE and not reporting (last seen: "
                f"{machine.get('last_seen', 'unknown')}). There is no live "
                f"prediction for it.")

    shap = machine.get("shap_values") or []
    drivers = ", ".join(
        f"{_clean(d['feature'])} ({d['contribution_pct']:.0f}%, {d['direction']})"
        for d in shap[:3]
    ) or "none available"
    life = machine.get("life") or {}
    sensors = machine.get("sensors") or {}
    override = machine.get("override") or {}
    wear = machine.get("wear") or {}
    tool_changes = machine.get("tool_changes") or []
    last_change = tool_changes[-1] if tool_changes else None

    lines = [
        f"The machine currently open is {machine.get('name')} in "
        f"{machine.get('location', 'an unspecified bay')}, state "
        f"{machine.get('state')}, tool material {machine.get('tool_material')}, "
        f"work material grade {machine.get('material_type')}.",
        f"- Scrap risk (calibrated probability from live signature): "
        f"{machine.get('risk_pct', 0):.0f}% (status: {machine.get('status')})",
        f"- Top SHAP drivers for the scrap-risk reading: {drivers}",
        f"- Tool runtime so far: {sensors.get('tool_runtime', 0):.0f} min, "
        f"expected tool life: {life.get('expected_tool_life_min', 0):.0f} min, "
        f"life consumed: {life.get('life_consumed_pct', 0):.0f}%",
        f"- Physics-based remaining life estimate: "
        f"{machine.get('est_time_to_failure', 'unknown')} "
        f"(range {_fmt(life.get('remaining_low_min', 0))}-"
        f"{_fmt(life.get('remaining_high_min', 0))})",
        f"- Recommended action: {override.get('text', 'none')}",
        f"- Scrap-cost exposure at current risk: ${machine.get('cost_impact', 0):.0f}",
    ]
    # Measured tool wear - a SEPARATE model from scrap risk above, trained on
    # real measured wear rather than a synthetic benchmark. Told to the model
    # explicitly as separate so it never conflates the two numbers in an answer.
    if wear.get("available"):
        rul = (f"{wear['rul_min']} min (range {wear['rul_low_min']}-{wear['rul_high_min']} min)"
               if wear.get("rul_min") is not None else "still establishing a trend")
        lines.append(
            f"- Measured tool wear (flank wear, a DIFFERENT model from scrap risk "
            f"above, trained on real measured wear): {wear['wear_mm']} mm of "
            f"{wear['limit_mm']} mm ISO limit ({wear['wear_pct_of_limit']:.0f}%), "
            f"status {wear['status']}. Time until change-out alert: {rul}."
        )
    else:
        lines.append(f"- Measured tool wear: not available right now "
                     f"({wear.get('reason', 'no reading')}).")
    if last_change:
        lines.append(
            f"- Last tool change: {last_change['runtime_at_change']:.0f} min "
            f"runtime, predicted risk {last_change['predicted_risk_at_change']:.0f}%, "
            f"{'was worn' if last_change.get('was_actually_worn') else 'was fine'}."
        )
    return "\n".join(lines)


def _fleet_context(fleet: List[dict]) -> str:
    if not fleet:
        return "This account has no machines connected yet."
    lines = ["Fleet snapshot (every machine on this account right now):"]
    for m in fleet:
        if m.get("state") == "OFFLINE":
            lines.append(f"- {m.get('name')}: OFFLINE, no signal")
        else:
            w = m.get("wear") or {}
            wear_bit = (f", measured wear {w['wear_mm']}mm ({w['status']})"
                       if w.get("available") else "")
            lines.append(
                f"- {m.get('name')} ({m.get('location', '')}): {m.get('state')}, "
                f"{m.get('risk_pct', 0):.0f}% scrap risk, "
                f"{m.get('est_time_to_failure', 'unknown')} life left{wear_bit}"
            )
    return "\n".join(lines)


def _build_messages(system: str, question: str, history: List[dict]) -> List[dict]:
    messages = [{"role": "system", "content": system}]
    for h in history:
        text = (h.get("text") or "").strip()
        if not text:
            continue
        role = "assistant" if h.get("role") == "assistant" else "user"
        messages.append({"role": role, "content": text})
    messages.append({"role": "user", "content": question})
    return messages


def _answer_with_llm(question: str, machine: Optional[dict],
                     fleet: List[dict], history: List[dict]) -> str:
    if _client is None:
        raise RuntimeError("No Groq credentials configured for the chatbot.")

    system = f"{SYSTEM_PROMPT}\n\n{_fleet_context(fleet)}\n\n{_machine_context(machine)}"
    response = _client.chat.completions.create(
        model=_GROQ_MODEL,
        max_completion_tokens=1024,
        messages=_build_messages(system, question, history),
    )
    answer = (response.choices[0].message.content or "").strip()
    if not answer:
        raise RuntimeError("Empty response from the model.")
    return answer


def answer_question(question: str, machine: Optional[dict] = None,
                    fleet: Optional[List[dict]] = None,
                    history: Optional[List[dict]] = None) -> str:
    """
    machine: the currently open machine snapshot (may be None on the
             dashboard-level chat)
    fleet:   all machine snapshots, for cross-machine questions
    history: prior turns in this conversation, as [{"role", "text"}, ...]
    """
    try:
        return _answer_with_llm(question, machine, fleet or [], history or [])
    except Exception as e:
        print(f"[Metrik] Chatbot fell back to the rule-based responder "
              f"({type(e).__name__}: {e})")
        return _answer_question_rule_based(question, machine, fleet or [])


# ---------------------------------------------------------------------------
# Fallback: the original keyword-matched responder. Used only when no
# Claude credentials are configured, or the live call fails.
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


def _answer_question_rule_based(question: str, machine: Optional[dict] = None,
                                fleet: Optional[List[dict]] = None) -> str:
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
        return (f"{name} is at {risk:.0f}% scrap risk. The three largest "
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
        return (f"At {risk:.0f}% scrap risk the scrap-cost exposure on "
                f"{name} is approximately ${machine['cost_impact']:.0f} - that is "
                f"the expected value of parts likely to go dimensionally out of "
                f"tolerance before the tool is changed. A planned tool change "
                f"costs a few minutes of spindle time; an unplanned one costs the "
                f"part, the rework and the downtime.")

    # fallback
    return (f"I can tell you why {name} is at {risk:.0f}%, what to do about it, "
            f"when to change the tool, or what the cost exposure is. I can also "
            f"explain how the model and the SHAP chart work. Which would help?")
