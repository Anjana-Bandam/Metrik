import React, { useEffect, useState, useCallback, useRef } from "react";
import { Info } from "lucide-react";
import GaugeChart from "./GaugeChart.jsx";
import ShapChart from "./ShapChart.jsx";
import { api } from "../api.js";

const SLIDERS = [
  { key: "spindle_speed", label: "Spindle speed", unit: "rpm", min: 800, max: 2400, step: 10, def: 1500 },
  { key: "feed_rate", label: "Feed rate / load", unit: "Nm", min: 5, max: 80, step: 1, def: 40 },
  { key: "depth_of_cut", label: "Depth of cut", unit: "mm", min: 0.2, max: 3, step: 0.1, def: 1.2 },
  { key: "tool_runtime", label: "Tool runtime so far", unit: "min", min: 0, max: 280, step: 1, def: 60 },
];
const MATERIALS = [["L", "Soft"], ["M", "Medium"], ["H", "Hard"]];
const TOOLS = [["carbide", "Carbide"], ["hss", "HSS"], ["ceramic", "Ceramic"]];

export default function SimulatorPanel() {
  const [v, setV] = useState(() => Object.fromEntries(SLIDERS.map((s) => [s.key, s.def])));
  const [material, setMaterial] = useState("M");
  const [tool, setTool] = useState("carbide");
  const [res, setRes] = useState(null);
  const [loading, setLoading] = useState(false);
  const timer = useRef(null);

  const run = useCallback((payload) => {
    setLoading(true);
    api.predict(payload).then(setRes).catch(() => {}).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    clearTimeout(timer.current);
    timer.current = setTimeout(
      () => run({ ...v, material_type: material, tool_material: tool }), 200);
    return () => clearTimeout(timer.current);
  }, [v, material, tool, run]);

  return (
    <div className="grid xl:grid-cols-[400px_1fr] gap-5">
      {/* Controls */}
      <div className="card p-6 flex flex-col gap-6 h-fit">
        <div className="flex items-start gap-2.5 p-3.5 rounded-2xl bg-violet-400/12">
          <Info size={15} className="text-violet-500 dark:text-violet-300 shrink-0 mt-0.5" />
          <p className="text-xs t-secondary leading-relaxed">
            These are the values a programmer sets in CAM before the job runs.
            Nothing here touches a live machine.
          </p>
        </div>

        <div>
          <label className="label-cap">Work material</label>
          <div className="flex gap-2 mt-2">
            {MATERIALS.map(([val, l]) => (
              <button key={val} onClick={() => setMaterial(val)}
                className={`flex-1 py-2.5 rounded-2xl text-xs font-semibold border transition-colors ${
                  material === val ? "bg-lime-400 border-lime-400 text-ink-950"
                  : "border-cream-300 dark:border-white/12 t-secondary hover:border-lime-400"
                }`}>{l}</button>
            ))}
          </div>
        </div>

        <div>
          <label className="label-cap">Tool material</label>
          <div className="flex gap-2 mt-2">
            {TOOLS.map(([val, l]) => (
              <button key={val} onClick={() => setTool(val)}
                className={`flex-1 py-2.5 rounded-2xl text-xs font-semibold border transition-colors ${
                  tool === val ? "bg-lime-400 border-lime-400 text-ink-950"
                  : "border-cream-300 dark:border-white/12 t-secondary hover:border-lime-400"
                }`}>{l}</button>
            ))}
          </div>
        </div>

        {SLIDERS.map((s) => {
          const val = v[s.key];
          const pct = ((val - s.min) / (s.max - s.min)) * 100;
          return (
            <div key={s.key}>
              <div className="flex items-baseline justify-between mb-2.5">
                <label className="text-sm font-semibold t-primary">{s.label}</label>
                <span className="telemetry text-sm font-bold t-primary">
                  {val}<span className="t-faint text-xs ml-1">{s.unit}</span>
                </span>
              </div>
              <input type="range" className="dial" style={{ "--fill": `${pct}%` }}
                min={s.min} max={s.max} step={s.step} value={val}
                onChange={(e) => setV((p) => ({ ...p, [s.key]: Number(e.target.value) }))} />
            </div>
          );
        })}
      </div>

      {/* Results */}
      <div className="flex flex-col gap-5">
        <div className="grid md:grid-cols-2 gap-5">
          <div className="card p-5">
            <p className="label-cap mb-1">Projected wear risk</p>
            <GaugeChart value={res?.risk_pct ?? 0} band={res?.status} height={240}
              low={res ? `${Math.round(res.life.remaining_low_min)}m` : undefined}
              high={res ? `${Math.round(res.life.remaining_high_min)}m` : undefined} />
          </div>
          <div className="card p-5">
            <p className="label-cap mb-1">What's driving it</p>
            <ShapChart shapValues={res?.shap_values ?? []} height={240} />
          </div>
        </div>

        {/* Taylor physics readout — the differentiator, made visible */}
    {/* Risk decomposition + Taylor physics — the two independent signals */}
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            ["Signature risk (ML)", res?.ml_risk_pct ?? "—", "%",
             "XGBoost on live parameters"],
            ["Life-used risk (physics)", res?.physics_risk_pct ?? "—", "%",
             "from Taylor consumed life"],
            ["Expected tool life", res?.life.expected_tool_life_min ?? "—", "min",
             "Taylor: V·Tⁿ = C"],
            ["Life remaining", res?.life.remaining_min ?? "—", "min",
             `at ${res?.life.cutting_speed_m_min ?? "—"} m/min`],
          ].map(([label, val, unit, sub]) => (
            <div key={label} className="card p-4">
              <p className="label-cap">{label}</p>
              <p className="telemetry text-2xl font-bold t-primary mt-1.5">
                {val}<span className="text-xs t-faint ml-1">{unit}</span>
              </p>
              <p className="telemetry text-[10px] t-faint mt-1">{sub}</p>
            </div>
          ))}
        </div>

        <div className="card p-4 flex items-start gap-3">
          <span className="w-1.5 self-stretch rounded-full bg-violet-400 shrink-0" />
          <p className="text-xs t-secondary leading-relaxed">
            The headline score combines both signals. A tool can look completely
            normal on live telemetry while sitting at 98% of its expected life —
            which is exactly when it starts putting parts out of tolerance. Neither
            signal alone catches that.
          </p>
        </div>

        <div className="card-invert p-5">
          <p className="label-cap !text-cream-200/55 mb-2">Metrik assessment</p>
          {loading && !res ? (
            <div className="space-y-2"><div className="skeleton h-3 w-full" />
              <div className="skeleton h-3 w-3/4" /></div>
          ) : (
            <p className="text-sm leading-relaxed text-cream-100">{res?.narrative}</p>
          )}
        </div>
      </div>
    </div>
  );
}