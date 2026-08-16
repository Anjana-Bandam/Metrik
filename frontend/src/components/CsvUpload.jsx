import React, { useState } from "react";
import { Upload, FileSpreadsheet } from "lucide-react";
import { api } from "../api.js";

const RISK_COLOR = { green: "text-ok", yellow: "text-warn", red: "text-danger" };

export default function CsvUpload() {
  const [rows, setRows] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const handleFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const { results } = await api.predictCsv(file);
      setRows(results);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  };

  return (
    <div className="card p-5">
      <div className="flex items-center gap-2 mb-1">
        <FileSpreadsheet size={16} className="text-violet-500 dark:text-violet-300" />
        <p className="font-display font-bold t-primary">Test with your own CSV</p>
      </div>
      <p className="text-sm t-muted mb-4">
        Upload a CSV with your own values — spindle_speed, spindle_torque, tool_runtime,
        depth_of_cut, material_type, tool_material — and see the model respond to
        numbers nobody pre-loaded.
      </p>

      <label className="btn-outline inline-flex cursor-pointer">
        <Upload size={15} />
        {busy ? "Processing..." : "Choose CSV file"}
        <input type="file" accept=".csv" onChange={handleFile} className="hidden" disabled={busy} />
      </label>

      {error && <p className="text-sm text-danger mt-3">{error}</p>}

      {rows && (
        <div className="mt-5 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left border-b border-cream-300 dark:border-white/10">
                <th className="py-2 pr-4 t-faint text-xs uppercase">Row</th>
                <th className="py-2 pr-4 t-faint text-xs uppercase">Risk</th>
                <th className="py-2 pr-4 t-faint text-xs uppercase">Status</th>
                <th className="py-2 pr-4 t-faint text-xs uppercase">Life left</th>
                <th className="py-2 pr-4 t-faint text-xs uppercase">Top driver</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.row} className="border-b border-cream-200 dark:border-white/5">
                  <td className="py-2 pr-4 t-primary">{r.row}</td>
                  <td className={`py-2 pr-4 telemetry font-bold ${RISK_COLOR[r.status] || ""}`}>
                    {r.risk_pct}%
                  </td>
                  <td className="py-2 pr-4 t-secondary capitalize">{r.status}</td>
                  <td className="py-2 pr-4 t-secondary">{r.est_time_to_failure}</td>
                  <td className="py-2 pr-4 t-secondary">
                    {r.top_driver?.replace(/\s*\[.*\]/, "") || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}