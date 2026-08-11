import React from "react";
import { AlertTriangle, Wrench, Radio, PowerOff, Activity, MapPin } from "lucide-react";
import Sparkline from "./Sparkline.jsx";
import { STATE_STYLE, RISK_STYLE } from "../api.js";

const STATE_ICON = {
  RUNNING: Activity, IDLE: Radio, TOOL_CHANGE: Wrench, OFFLINE: PowerOff,
};

export default function MachineCard({ machine, onOpen }) {
  const st = STATE_STYLE[machine.state];
  const rk = RISK_STYLE[machine.status] || RISK_STYLE.green;
  const StateIcon = STATE_ICON[machine.state];
  const live = machine.state === "RUNNING";
  const offline = machine.state === "OFFLINE";
  const urgent = live && machine.status === "red";

  const sparkColor =
    machine.status === "red" ? "#FF6B5A" :
    machine.status === "yellow" ? "#FFC24B" : "#D6F84C";

  return (
    <button onClick={() => onOpen(machine)}
      className={`card p-5 text-left flex flex-col gap-4 transition-all duration-200
                  hover:-translate-y-1 hover:shadow-lift animate-rise
                  ${urgent ? "ring-2 ring-danger/40" : ""}
                  ${offline ? "opacity-60" : ""}`}>

      {/* Head: name, bay, state */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="font-display font-bold text-[15px] t-primary truncate">
            {machine.name}
          </h3>
          <p className="flex items-center gap-1 text-xs t-faint mt-0.5">
            <MapPin size={11} /> {machine.location}
            <span className="mx-1">·</span> {machine.source}
          </p>
        </div>
        <span className={`chip ${st.chip} shrink-0`}>
          <StateIcon size={11} strokeWidth={2.5} />
          {st.label}
        </span>
      </div>

      {/* Risk number, or an honest blank when there's no signal */}
      {offline ? (
        <div className="py-3">
          <p className="telemetry text-[34px] font-bold leading-none t-faint">—</p>
          <p className="text-xs t-faint mt-1.5">No live signal to score</p>
        </div>
      ) : (
        <>
          <div className="flex items-end justify-between gap-3">
            <div>
              <div className="flex items-end gap-1.5">
                <span className={`telemetry text-[38px] font-bold leading-none ${
                  machine.status === "green" ? "t-primary" : rk.text}`}>
                  {machine.risk_pct.toFixed(0)}
                </span>
                <span className="text-sm t-faint mb-1">%</span>
              </div>
              <p className="text-xs t-muted mt-1">wear probability</p>
            </div>
            <div className="w-24 shrink-0">
              <Sparkline data={machine.risk_history} color={sparkColor} height={34} />
            </div>
          </div>

          {/* Tool life consumed */}
          <div>
            <div className="flex justify-between text-[11px] t-muted mb-1.5">
              <span>Tool life used</span>
              <span className="telemetry">{machine.life.life_consumed_pct.toFixed(0)}%</span>
            </div>
            <div className="h-1.5 rounded-pill bg-cream-200 dark:bg-ink-600 overflow-hidden">
              <div className="h-full rounded-pill transition-all duration-500"
                style={{
                  width: `${Math.min(machine.life.life_consumed_pct, 100)}%`,
                  backgroundColor: sparkColor,
                }} />
            </div>
          </div>
        </>
      )}

      {/* Foot: telemetry */}
      <div className="hairline pt-3.5 grid grid-cols-3 gap-2 text-xs">
        {[
          ["Depth", `${machine.sensors.depth_of_cut}`, "mm"],
          ["Spindle", live ? `${machine.sensors.spindle_speed.toFixed(0)}` : "—", "rpm"],
          ["Left", offline ? "—" : machine.est_time_to_failure, ""],
        ].map(([k, v, u]) => (
          <div key={k}>
            <p className="t-faint text-[10px] uppercase tracking-wide">{k}</p>
            <p className="telemetry font-semibold t-primary mt-0.5">
              {v}<span className="t-faint text-[10px] ml-0.5">{u}</span>
            </p>
          </div>
        ))}
      </div>

      {urgent && (
        <div className="flex items-center gap-2 px-3 py-2.5 rounded-2xl bg-danger/12 text-danger text-xs font-semibold">
          <AlertTriangle size={13} className="shrink-0" />
          <span>Scrap exposure ${machine.cost_impact.toFixed(0)} · {machine.override.text.split(".")[0]}</span>
        </div>
      )}
    </button>
  );
}