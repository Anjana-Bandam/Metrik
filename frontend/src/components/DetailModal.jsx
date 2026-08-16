import React, { useState } from "react";
import {
  X, Download, Clock, DollarSign, Info, Wrench, Gauge as GaugeIcon,
  Check, BellOff, Radio, Activity, PowerOff, FastForward,
} from "lucide-react";
import GaugeChart from "./GaugeChart.jsx";
import ShapChart from "./ShapChart.jsx";
import ChatPanel from "./ChatPanel.jsx";
import ToolChangeModal from "./ToolChangeModal.jsx";
import { api, downloadJson, STATE_STYLE, RISK_STYLE } from "../api.js";
import { downloadMachinePdf } from "../reportPdf.js";
import { useAuth } from "../auth.jsx";
const STATES = [
  ["RUNNING", "Running", Activity],
  ["IDLE", "Idle", Radio],
  ["TOOL_CHANGE", "Tool change", Wrench],
  ["OFFLINE", "Offline", PowerOff],
];

export default function DetailModal({ machine, onClose, onRefresh }) {
  const { user } = useAuth();
  const [tcOpen, setTcOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("");

  if (!machine) return null;

  const st = STATE_STYLE[machine.state];
  const rk = RISK_STYLE[machine.status] || RISK_STYLE.green;
  const offline = machine.state === "OFFLINE";

  const wear = machine.wear;
  // Alert thresholds are model outputs, not UI constants — they move whenever
  // the model is recalibrated, so they arrive with the snapshot. The fallbacks
  // only cover an API older than this build.
  const bands = machine.risk_bands || { watch: 40, alert: 70 };

  const flash = (msg) => { setToast(msg); setTimeout(() => setToast(""), 2600); };

  const handleToolChange = async (worn, note) => {
    setBusy(true);
    try {
      await api.logToolChange(machine.machine_id, worn, note);
      setTcOpen(false);
      flash("Tool change logged. Runtime reset to zero.");
      onRefresh?.();
    } finally { setBusy(false); }
  };

  const handleAck = async (decision) => {
    setBusy(true);
    try {
      await api.acknowledge(machine.machine_id, decision, "");
      flash(decision === "accepted"
        ? "Acknowledged — recorded against your name."
        : "Dismissed — Metrik will keep monitoring.");
      onRefresh?.();
    } finally { setBusy(false); }
  };

  const handleState = async (state) => {
    setBusy(true);
    try { await api.setState(machine.machine_id, state); onRefresh?.(); }
    finally { setBusy(false); }
  };


const handleFastMode = async (enabled) => {
    setBusy(true);
    try {
      await api.setFastMode(machine.machine_id, enabled);
      flash(enabled ? "Fast simulation ON — watch the numbers climb." : "Back to normal speed.");
      onRefresh?.();
    } finally {
      setBusy(false);
    }
  };


  const sensors = [
    ["Spindle speed", machine.sensors.spindle_speed.toFixed(0), "rpm"],
    ["Spindle torque", machine.sensors.spindle_torque.toFixed(1), "Nm"],
    ["Depth of cut", machine.sensors.depth_of_cut, "mm"],
    ["Tool runtime", machine.sensors.tool_runtime.toFixed(0), "min"],
    ["Cutting speed", machine.life.cutting_speed_m_min, "m/min"],
    ["Process temp", machine.sensors.process_temperature.toFixed(1), "K"],
  ];

  return (
    <>
      <div className="fixed inset-0 z-50 grid place-items-center p-3 sm:p-6 bg-ink-950/60 backdrop-blur-sm"
           onClick={onClose}>
        <div className="card-raised w-full max-w-5xl max-h-[92vh] overflow-y-auto"
             onClick={(e) => e.stopPropagation()}>

          {/* Header */}
          <div className="sticky top-0 z-10 flex items-start justify-between gap-4 p-6
                          bg-white dark:bg-ink-700 border-b border-cream-300/70 dark:border-white/[0.07]">
            <div className="min-w-0">
              <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                <span className={`chip ${st.chip}`}>{st.label}</span>
                {!offline && <span className={`chip ${rk.chip}`}>{rk.label}</span>}
                <span className="chip chip-neutral">{machine.source}</span>
              </div>
              <h2 className="font-display font-bold text-2xl t-primary tracking-[-0.02em] truncate">
                {machine.name}
              </h2>
              <p className="text-xs t-muted mt-0.5">
                {machine.location} · {machine.tool_material} tool · material grade {machine.material_type}
              </p>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <button
                onClick={() => handleFastMode(!machine.fast_mode)}
                disabled={busy || machine.state !== "RUNNING"}
                title={machine.state !== "RUNNING"
                  ? "Set this machine to Running first"
                  : "Toggle fast simulation speed"}
                className={`flex items-center gap-1.5 px-3.5 h-10 rounded-pill text-xs font-semibold transition-colors ${
                  machine.fast_mode
                    ? "bg-violet-500 text-white"
                    : "bg-cream-200 dark:bg-ink-600 t-secondary hover:bg-cream-300 dark:hover:bg-ink-500"
                } ${busy || machine.state !== "RUNNING" ? "opacity-40 cursor-not-allowed" : ""}`}>
                <FastForward size={14} />
                {machine.fast_mode ? "Fast: ON" : "Fast sim"}
              </button>

              <button onClick={onClose} className="btn-ghost w-10 h-10 !p-0 rounded-pill">
                <X size={18} />
              </button>
            </div>
          </div>

          {/* Recommended action banner — the thing an operator actually acts on */}
          {!offline && (
            <div className={`mx-6 mt-6 p-5 rounded-card flex flex-col sm:flex-row sm:items-center gap-4 ${
              machine.status === "red" ? "bg-danger/10"
              : machine.status === "yellow" ? "bg-warn/10" : "bg-lime-400/15"}`}>
              <div className="flex-1 min-w-0">
                <p className="label-cap mb-1">Recommended action</p>
                <p className="text-sm font-semibold t-primary leading-snug">
                  {machine.override.text}
                </p>
                {machine.override.override_pct < 100 && (
                  <p className="text-xs t-muted mt-1.5">
                    Set the feed override dial on the control panel to{" "}
                    <span className="telemetry font-bold t-primary">
                      {machine.override.override_pct}%
                    </span>
                  </p>
                )}
              </div>
              <div className="flex gap-2 shrink-0">
                <button onClick={() => handleAck("accepted")} disabled={busy}
                  className="btn-dark text-xs px-3.5 py-2">
                  <Check size={14} /> Acknowledge
                </button>
                <button onClick={() => handleAck("dismissed")} disabled={busy}
                  className="btn-outline text-xs px-3.5 py-2">
                  <BellOff size={14} /> Dismiss
                </button>
              </div>
            </div>
          )}

          <div className="p-6 grid lg:grid-cols-2 gap-5">
            {/* The two headline numbers, side by side and drawn as the same
                instrument so they can be read together. They come from two
                different models validated on two different datasets, which is
                why each carries its own provenance line rather than sharing
                one caption. */}
            <div className="card p-5 lg:col-span-2">
              <div className="grid sm:grid-cols-2 gap-5 sm:divide-x divide-cream-200 dark:divide-ink-600">

                {/* Tool wear — the physical measurement */}
                <div className="sm:pr-5">
                  <div className="flex items-baseline justify-between gap-2 mb-1">
                    <p className="label-cap">Tool wear</p>
                    <span className="text-[10px] t-faint">flank wear · VB</span>
                  </div>

                  {offline ? (
                    <div className="h-[240px] grid place-items-center text-center">
                      <p className="text-sm t-muted max-w-[220px]">
                        No live signal to measure wear from.
                      </p>
                    </div>
                  ) : wear?.available ? (
                    <GaugeChart
                      value={wear.wear_mm}
                      max={wear.limit_mm}
                      suffix=" mm"
                      decimals={3}
                      watch={wear.watch_mm}
                      alert={wear.alert_mm}
                      band={wear.status}
                      height={240}
                    />
                  ) : (
                    <div className="h-[240px] grid place-items-center text-center px-4">
                      <div>
                        <Wrench size={26} className="mx-auto t-faint mb-3" />
                        <p className="text-sm t-muted">{wear?.reason || "No wear reading yet."}</p>
                      </div>
                    </div>
                  )}

                  {/* Remaining useful life — the number an operator actually
                      acts on. Wear in mm says how bad it is; this says how long
                      they have. Shown as a range because a point estimate would
                      claim precision the projection does not have. */}
                  <div className="hairline pt-4 mt-2">
                    <div className="flex items-baseline justify-between gap-2">
                      <p className="text-[10px] t-faint uppercase tracking-wide">
                        Time until tool change
                      </p>
                      {wear?.rul_min != null && (
                        <span className="text-[10px] t-faint telemetry">
                          {wear.rul_low_min}–{wear.rul_high_min} min
                        </span>
                      )}
                    </div>
                    <p className="telemetry text-2xl font-bold t-primary mt-0.5">
                      {wear?.rul_min != null
                        ? <>{wear.rul_min}<span className="text-xs t-faint ml-1">min</span></>
                        : <span className="text-base t-muted font-normal">
                            {wear?.available ? "Establishing trend…" : "—"}
                          </span>}
                    </p>
                  </div>

                  <div className="hairline pt-3 mt-3 grid grid-cols-2 gap-3">
                    <div className="flex items-start gap-2">
                      <GaugeIcon size={14} className="t-faint mt-0.5 shrink-0" />
                      <div className="min-w-0">
                        <p className="telemetry text-sm font-bold t-primary">
                          {wear?.available ? `${wear.wear_pct_of_limit.toFixed(0)}%` : "—"}
                        </p>
                        <p className="text-[10px] t-faint leading-tight">of ISO 8688 limit</p>
                      </div>
                    </div>
                    <div className="flex items-start gap-2">
                      <Wrench size={14} className="t-faint mt-0.5 shrink-0" />
                      <div className="min-w-0">
                        <p className="telemetry text-sm font-bold t-primary">
                          {wear?.wear_rate_mm_per_min
                            ? `${(wear.wear_rate_mm_per_min * 1000).toFixed(2)} µm`
                            : "—"}
                        </p>
                        <p className="text-[10px] t-faint leading-tight">wear per minute</p>
                      </div>
                    </div>
                  </div>

                  <p className="text-[10px] t-faint leading-relaxed mt-3">
                    Estimated from cutting force, vibration and acoustic emission.
                    Trained on real PHM&nbsp;2010 cutters, ±16&nbsp;µm.
                    {wear?.alert_mm && (
                      <> Change-out alert at {wear.alert_mm}&nbsp;mm, set below the{" "}
                      {wear.true_change_point_mm}&nbsp;mm limit because the model
                      under-reads on a heavily worn edge — validated to catch
                      100% of worn tools.</>
                    )}
                  </p>
                </div>

                {/* Scrap risk — the calibrated probability */}
                <div className="sm:pl-5">
                  <div className="flex items-baseline justify-between gap-2 mb-1">
                    <p className="label-cap">Scrap risk</p>
                    <span className="text-[10px] t-faint">calibrated probability</span>
                  </div>

                  {offline ? (
                    <div className="h-[240px] grid place-items-center text-center">
                      <div>
                        <PowerOff size={26} className="mx-auto t-faint mb-3" />
                        <p className="text-sm t-muted max-w-[220px]">
                          No live signal. Metrik does not estimate risk for machines
                          it can't hear from.
                        </p>
                      </div>
                    </div>
                  ) : (
                    <GaugeChart
                      value={machine.risk_pct}
                      max={100}
                      suffix="%"
                      watch={bands.watch}
                      alert={bands.alert}
                      band={machine.status}
                      height={240}
                      low={`${Math.round(machine.life.remaining_low_min)}m`}
                      high={`${Math.round(machine.life.remaining_high_min)}m`}
                    />
                  )}

                  <div className="hairline pt-4 mt-2 grid grid-cols-3 gap-3">
                    {[
                      [Clock, machine.est_time_to_failure, "est. life left"],
                      [GaugeIcon, `${machine.life.life_consumed_pct.toFixed(0)}%`, "life consumed"],
                      [DollarSign, `$${machine.cost_impact.toFixed(0)}`, "scrap exposure"],
                    ].map(([Icon, val, lab]) => (
                      <div key={lab} className="flex items-start gap-2">
                        <Icon size={14} className="t-faint mt-0.5 shrink-0" />
                        <div className="min-w-0">
                          <p className="telemetry text-sm font-bold t-primary">{offline ? "—" : val}</p>
                          <p className="text-[10px] t-faint leading-tight">{lab}</p>
                        </div>
                      </div>
                    ))}
                  </div>

                  <p className="text-[10px] t-faint leading-relaxed mt-3">
                    Probability this cut ends in a wear-driven scrap event.
                    Amber from {bands.watch}%, act from {bands.alert}%.
                  </p>
                </div>
              </div>
            </div>

            {/* SHAP — full width. It is a horizontal bar chart with long
                feature names, so a half-width column wastes the labels and
                leaves an empty half-row beside it. */}
            <div className="card p-5 lg:col-span-2">
              <p className="label-cap mb-1">What's driving the scrap-risk score</p>
              <ShapChart shapValues={machine.shap_values} height={260} />
              <p className="text-[11px] t-faint mt-3 leading-relaxed">
                Contributions are for this single prediction and re-computed
                every reading — not a fixed model-wide ranking. These explain the
                scrap-risk classifier; the wear estimate is a separate model.
              </p>
            </div>

            {/* Sensors */}
            <div className="card p-5 lg:col-span-2">
              <div className="flex items-center justify-between mb-3.5">
                <p className="label-cap">Live sensor readout</p>
                <p className="text-[11px] t-faint">via {machine.source}</p>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5">
                {sensors.map(([label, value, unit]) => {
                  const est = machine.estimated_fields?.some((f) =>
                    f.toLowerCase().includes(label.toLowerCase().split(" ")[0]));
                  return (
                    <div key={label} className="px-3 py-3 rounded-2xl bg-cream-100 dark:bg-ink-800">
                      <p className="text-[10px] t-faint uppercase tracking-wide flex items-center gap-1">
                        {label}
                        {est && <Info size={10} className="text-warn" title="Estimated — no sensor present" />}
                      </p>
                      <p className="telemetry text-sm font-bold t-primary mt-1">
                        {value}<span className="text-[10px] t-faint ml-0.5">{unit}</span>
                      </p>
                    </div>
                  );
                })}
              </div>
              {machine.estimated_fields?.length > 0 && (
                <p className="text-[11px] text-warn mt-3">
                  Fields marked with a badge are estimated from other sensors —
                  this machine doesn't report them directly.
                </p>
              )}
            </div>

            {/* Assistant */}
            <div className="lg:col-span-2 grid lg:grid-cols-[1fr_300px] gap-5">
              <ChatPanel machineId={machine.machine_id} seedNarrative={machine.narrative} />

              <div className="flex flex-col gap-3">
                <button onClick={() => setTcOpen(true)} className="btn-primary w-full">
                  <Wrench size={15} /> Log tool change
                </button>
                <button onClick={() => downloadMachinePdf(machine, user?.company)}
                  className="btn-outline w-full">
                  <Download size={15} /> Download report (PDF)
                </button>
                <button
                  onClick={() => downloadJson(
                    api.exportMachineUrl(machine.machine_id),
                    `metrik_${machine.machine_id}_report.json`)}
                  className="btn-ghost w-full text-xs">
                  Raw JSON (for integrations)
                </button>

                <div className="card p-4">
                  <p className="label-cap mb-2.5">Reported machine state</p>
                  <div className="grid grid-cols-2 gap-1.5">
                    {STATES.map(([val, label, Icon]) => (
                      <button key={val} onClick={() => handleState(val)} disabled={busy}
                        className={`flex items-center gap-1.5 px-2.5 py-2 rounded-xl text-[11px]
                                    font-semibold border transition-colors ${
                          machine.state === val
                            ? "bg-ink-900 dark:bg-lime-400 text-cream-50 dark:text-ink-950 border-transparent"
                            : "border-cream-300 dark:border-white/12 t-secondary hover:border-lime-400"
                        }`}>
                        <Icon size={12} /> {label}
                      </button>
                    ))}
                  </div>
                  <p className="text-[10px] t-faint mt-2.5 leading-relaxed">
                    Mirrors what the machine reports. Metrik never commands a
                    state change.
                  </p>
                </div>
                

               

                {machine.tool_changes?.length > 0 && (
                  <div className="card p-4">
                    <p className="label-cap mb-2.5">Recent tool changes</p>
                    <div className="space-y-2">
                      {machine.tool_changes.slice(-3).reverse().map((t) => (
                        <div key={t.event_id} className="text-[11px] t-muted">
                          <span className="telemetry t-primary font-semibold">
                            {t.runtime_at_change.toFixed(0)} min
                          </span>
                          {" · predicted "}
                          <span className="telemetry">{t.predicted_risk_at_change.toFixed(0)}%</span>
                          {" · "}
                          <span className={t.was_actually_worn ? "text-danger" : "text-ok"}>
                            {t.was_actually_worn ? "was worn" : "still good"}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      <ToolChangeModal machine={machine} open={tcOpen} busy={busy}
        onClose={() => setTcOpen(false)} onSubmit={handleToolChange} />

      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[70] animate-rise
                        px-5 py-3 rounded-pill bg-ink-900 dark:bg-lime-400
                        text-cream-50 dark:text-ink-950 text-sm font-semibold shadow-lift">
          {toast}
        </div>
      )}
    </>
  );
}