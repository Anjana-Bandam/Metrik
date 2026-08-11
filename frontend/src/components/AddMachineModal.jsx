import React, { useState } from "react";
import { X, Plus } from "lucide-react";

const MATERIALS = [["L", "Soft"], ["M", "Medium"], ["H", "Hard"]];
const TOOLS = [["carbide", "Carbide"], ["hss", "HSS"], ["ceramic", "Ceramic"]];
const SOURCES = ["OPC UA", "MTConnect", "FOCAS", "Retrofit sensor", "CSV upload"];

export default function AddMachineModal({ open, onClose, onCreate, creating }) {
  const [f, setF] = useState({
    name: "", material_type: "M", tool_material: "carbide",
    location: "Bay 1", source: "OPC UA",
  });
  if (!open) return null;
  const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

  return (
    <div className="fixed inset-0 z-50 grid place-items-center p-4 bg-ink-950/60 backdrop-blur-sm"
         onClick={onClose}>
      <form onClick={(e) => e.stopPropagation()}
        onSubmit={(e) => { e.preventDefault(); if (f.name.trim()) onCreate(f); }}
        className="card-raised w-full max-w-md p-6">

        <div className="flex items-center justify-between mb-5">
          <div>
            <h3 className="font-display font-bold text-lg t-primary">Connect a machine</h3>
            <p className="text-xs t-muted mt-0.5">It joins your plant with a fresh tool at 0 min.</p>
          </div>
          <button type="button" onClick={onClose} className="btn-ghost w-9 h-9 !p-0 rounded-pill">
            <X size={17} />
          </button>
        </div>

        <label className="label-cap">Machine name</label>
        <input autoFocus className="field mt-1.5 mb-4" placeholder="VMC-07 Haas VF3"
          value={f.name} onChange={(e) => set("name", e.target.value)} required />

        <div className="grid grid-cols-2 gap-3 mb-4">
          <div>
            <label className="label-cap">Bay / cell</label>
            <input className="field mt-1.5" placeholder="Bay 2"
              value={f.location} onChange={(e) => set("location", e.target.value)} />
          </div>
          <div>
            <label className="label-cap">Data source</label>
            <select className="field mt-1.5" value={f.source}
              onChange={(e) => set("source", e.target.value)}>
              {SOURCES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
        </div>

        <label className="label-cap">Work material grade</label>
        <div className="flex gap-2 mt-1.5 mb-4">
          {MATERIALS.map(([v, l]) => (
            <button type="button" key={v} onClick={() => set("material_type", v)}
              className={`flex-1 py-2.5 rounded-2xl text-xs font-semibold border transition-colors ${
                f.material_type === v
                  ? "bg-lime-400 border-lime-400 text-ink-950"
                  : "border-cream-300 dark:border-white/12 t-secondary hover:border-lime-400"
              }`}>{l}</button>
          ))}
        </div>

        <label className="label-cap">Tool material</label>
        <div className="flex gap-2 mt-1.5 mb-6">
          {TOOLS.map(([v, l]) => (
            <button type="button" key={v} onClick={() => set("tool_material", v)}
              className={`flex-1 py-2.5 rounded-2xl text-xs font-semibold border transition-colors ${
                f.tool_material === v
                  ? "bg-lime-400 border-lime-400 text-ink-950"
                  : "border-cream-300 dark:border-white/12 t-secondary hover:border-lime-400"
              }`}>{l}</button>
          ))}
        </div>

        <button type="submit" disabled={!f.name.trim() || creating} className="btn-primary w-full">
          <Plus size={15} /> {creating ? "Connecting..." : "Connect machine"}
        </button>
        <p className="text-[11px] t-faint text-center mt-3">
          Tool material sets the Taylor life constants used for remaining-life estimates.
        </p>
      </form>
    </div>
  );
}