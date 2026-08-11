import React, { useState } from "react";
import { X, Wrench, Check, ThumbsUp, ThumbsDown } from "lucide-react";

/**
 * Operator confirms a physical tool change and reports whether the tool was
 * genuinely worn. That verdict is a labelled row Metrik can retrain on.
 */
export default function ToolChangeModal({ machine, open, onClose, onSubmit, busy }) {
  const [worn, setWorn] = useState(null);
  const [note, setNote] = useState("");

  if (!open || !machine) return null;

  return (
    <div className="fixed inset-0 z-[60] grid place-items-center p-4 bg-ink-950/60 backdrop-blur-sm"
         onClick={onClose}>
      <div className="card-raised w-full max-w-md p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between mb-5">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-violet-400/20 text-violet-500 dark:text-violet-300 grid place-items-center">
              <Wrench size={18} />
            </div>
            <div>
              <h3 className="font-display font-bold text-lg t-primary leading-tight">Log tool change</h3>
              <p className="text-xs t-muted">{machine.name}</p>
            </div>
          </div>
          <button onClick={onClose} className="btn-ghost w-9 h-9 !p-0 rounded-pill">
            <X size={17} />
          </button>
        </div>

        <div className="rounded-2xl bg-cream-100 dark:bg-ink-800 p-4 mb-5 grid grid-cols-2 gap-3">
          <div>
            <p className="label-cap">Runtime at change</p>
            <p className="telemetry font-bold t-primary mt-1">
              {machine.sensors.tool_runtime.toFixed(0)} min
            </p>
          </div>
          <div>
            <p className="label-cap">Metrik predicted</p>
            <p className="telemetry font-bold t-primary mt-1">
              {machine.risk_pct.toFixed(0)}% wear
            </p>
          </div>
        </div>

        <p className="text-sm font-semibold t-primary mb-1">
          Was the tool actually worn when you pulled it?
        </p>
        <p className="text-xs t-muted mb-3">
          Your answer becomes a training label — it's how Metrik gets more
          accurate for this specific plant.
        </p>

        <div className="flex gap-2 mb-5">
          {[
            [true, "Yes, worn", ThumbsUp],
            [false, "No, still good", ThumbsDown],
          ].map(([val, label, Icon]) => (
            <button key={String(val)} onClick={() => setWorn(val)}
              className={`flex-1 flex items-center justify-center gap-2 py-3 rounded-2xl
                          text-sm font-semibold border transition-all ${
                worn === val
                  ? "bg-lime-400 border-lime-400 text-ink-950"
                  : "border-cream-300 dark:border-white/12 t-secondary hover:border-lime-400"
              }`}>
              <Icon size={15} /> {label}
            </button>
          ))}
        </div>

        <label className="label-cap">Note (optional)</label>
        <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2}
          placeholder="e.g. flank wear visible on two flutes"
          className="field mt-1.5 mb-5 resize-none" />

        <div className="flex gap-2">
          <button onClick={onClose} className="btn-outline flex-1">Cancel</button>
          <button onClick={() => onSubmit(worn, note)} disabled={worn === null || busy}
            className="btn-primary flex-1">
            <Check size={15} /> {busy ? "Saving..." : "Confirm change"}
          </button>
        </div>

        <p className="text-[11px] t-faint text-center mt-4">
          Cumulative runtime resets to zero. Metrik does not restart the machine.
        </p>
      </div>
    </div>
  );
}