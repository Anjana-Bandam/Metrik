import React from "react";

/**
 * KPI tile. `variant="invert"` renders the dark-on-light emphasis tile that
 * the flux reference uses to break up a row of white cards.
 */
export default function KpiCard({ icon: Icon, label, value, unit, foot, tone = "lime", variant }) {
  const inverted = variant === "invert";
  const toneBg = {
    lime: "bg-lime-400 text-ink-950",
    danger: "bg-danger/15 text-danger",
    violet: "bg-violet-400/20 text-violet-500 dark:text-violet-300",
    ok: "bg-ok/15 text-ok",
  }[tone];

  return (
    <div className={`${inverted ? "card-invert" : "card"} p-5 flex flex-col gap-5 animate-rise`}>
      <div className="flex items-start justify-between gap-3">
        <span className={`text-[11px] font-semibold uppercase tracking-[0.08em] ${
          inverted ? "text-cream-200/55" : "t-muted"}`}>
          {label}
        </span>
        <div className={`w-9 h-9 rounded-xl grid place-items-center shrink-0 ${toneBg}`}>
          <Icon size={16} strokeWidth={2.3} />
        </div>
      </div>

      <div className="flex items-end gap-1.5">
        <span className={`telemetry font-display text-[34px] leading-none font-bold ${
          inverted ? "text-cream-50" : "t-primary"}`}>
          {value}
        </span>
        {unit && (
          <span className={`text-sm mb-1 ${inverted ? "text-cream-200/50" : "t-faint"}`}>
            {unit}
          </span>
        )}
      </div>

      {foot && (
        <span className={`text-xs ${inverted ? "text-cream-200/50" : "t-muted"}`}>{foot}</span>
      )}
    </div>
  );
}