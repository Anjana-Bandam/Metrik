import React from "react";
import { Monitor, Moon, Sun, ShieldCheck, Plug, Cpu } from "lucide-react";
import Header from "../components/Header.jsx";
import { useTheme } from "../theme.jsx";
import { useAuth } from "../auth.jsx";

const THEMES = [["light", "Light", Sun], ["dark", "Dark", Moon], ["system", "System", Monitor]];

const CONNECTORS = [
  ["OPC UA / umati", "Vendor-neutral IEC 62541. umati is the companion spec for machine tools.", true],
  ["MTConnect", "Widely deployed on CNC machine tools, especially North America.", true],
  ["FANUC FOCAS", "Direct API for FANUC and Robodrill controls.", true],
  ["Retrofit gateway", "Spindle current clamp or vibration sensor for machines with no digital port.", true],
  ["CSV upload", "Batch import for machines with no connectivity at all.", true],
];

export default function SettingsPage() {
  const { mode, setMode } = useTheme();
  const { user } = useAuth();

  return (
    <div className="flex-1 min-w-0">
      <Header title="Settings" subtitle="Appearance, connectors, and how Metrik works" />

      <div className="p-5 md:p-8 space-y-6 max-w-3xl">
        {/* Account */}
        <div className="card p-5">
          <h3 className="font-display font-bold t-primary mb-4">Plant account</h3>
          <div className="grid sm:grid-cols-3 gap-4">
            {[["Company", user?.company], ["Signed in as", user?.full_name],
              ["Role", user?.role]].map(([k, v]) => (
              <div key={k}>
                <p className="label-cap">{k}</p>
                <p className="text-sm font-semibold t-primary mt-1 capitalize">{v}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Appearance */}
        <div className="card p-5">
          <h3 className="font-display font-bold t-primary">Appearance</h3>
          <p className="text-sm t-muted mb-4 mt-0.5">How Metrik looks on this device.</p>
          <div className="grid grid-cols-3 gap-3">
            {THEMES.map(([val, label, Icon]) => (
              <button key={val} onClick={() => setMode(val)}
                className={`flex flex-col items-center gap-2 py-5 rounded-2xl border transition-colors ${
                  mode === val
                    ? "border-lime-400 bg-lime-400/12 text-lime-600 dark:text-lime-300"
                    : "border-cream-300 dark:border-white/12 t-secondary hover:border-lime-400"
                }`}>
                <Icon size={18} />
                <span className="text-xs font-semibold">{label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Connectors */}
        <div className="card p-5">
          <div className="flex items-center gap-2 mb-1">
            <Plug size={16} className="text-violet-500 dark:text-violet-300" />
            <h3 className="font-display font-bold t-primary">Machine connectors</h3>
          </div>
          <p className="text-sm t-muted mb-4">
            Metrik reads through an adapter layer, not one fixed protocol —
            because no single standard covers every shop floor.
          </p>
          <div className="space-y-2">
            {CONNECTORS.map(([name, desc, on]) => (
              <div key={name} className="flex items-start gap-3 p-3.5 rounded-2xl bg-cream-100 dark:bg-ink-800">
                <span className={`status-dot mt-1 ${on ? "bg-ok" : "bg-offline"}`} />
                <div className="min-w-0">
                  <p className="text-sm font-semibold t-primary">{name}</p>
                  <p className="text-xs t-muted mt-0.5 leading-relaxed">{desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* How it works */}
        <div className="card p-5">
          <div className="flex items-center gap-2 mb-3">
            <Cpu size={16} className="text-violet-500 dark:text-violet-300" />
            <h3 className="font-display font-bold t-primary">How the prediction works</h3>
          </div>
          <div className="space-y-3 text-sm t-secondary leading-relaxed">
            <p>
              <span className="font-semibold t-primary">Risk score.</span>{" "}
              An XGBoost classifier over machining parameters and runtime, class-weighted
              for the low failure rate in training data. Outputs a probability, never a
              hard yes/no.
            </p>
            <p>
              <span className="font-semibold t-primary">Remaining life.</span>{" "}
              Taylor's tool life equation (V·Tⁿ = C) gives a physics baseline from surface
              cutting speed, corrected for material hardness, depth of cut and load — then
              derated by the ML risk score. The confidence range widens as risk rises.
            </p>
            <p>
              <span className="font-semibold t-primary">Explanation.</span>{" "}
              SHAP values computed per prediction, normalised to 100%, so the chart shows
              this reading's drivers rather than a fixed global ranking.
            </p>
          </div>
        </div>

        {/* Guardrail */}
        <div className="card-invert p-5">
          <div className="flex items-center gap-2 mb-2">
            <ShieldCheck size={16} className="text-lime-400" />
            <h3 className="font-display font-bold text-cream-50">Safety guardrails</h3>
          </div>
          <ul className="text-sm text-cream-200/70 space-y-2 leading-relaxed">
            <li>· Metrik never starts, stops or reconfigures a machine. There is no control path.</li>
            <li>· Every prediction ships with a confidence range, never a bare number.</li>
            <li>· Feed override recommendations never increase feed and never drop below 70%.</li>
            <li>· Machines with no live signal show no score, rather than a guessed one.</li>
          </ul>
        </div>
      </div>
    </div>
  );
}