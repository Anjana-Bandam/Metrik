import React from "react";
import Plot from "react-plotly.js";
import { useTheme } from "../theme.jsx";
import { cleanFeature } from "../api.js";

export default function ShapChart({ shapValues = [], height = 240 }) {
  const { resolvedTheme } = useTheme();
  const dark = resolvedTheme === "dark";
  const text = dark ? "#F2F1E8" : "#141519";
  const grid = dark ? "rgba(255,255,255,0.06)" : "rgba(20,21,25,0.07)";

  if (!shapValues.length) {
    return (
      <div style={{ height }} className="grid place-items-center t-faint text-sm">
        No prediction to explain
      </div>
    );
  }

  // Top 6, ascending so the biggest driver lands at the top of the chart
  const sorted = [...shapValues]
    .sort((a, b) => b.contribution_pct - a.contribution_pct)
    .slice(0, 6)
    .reverse();

  const values = sorted.map((s) => s.contribution_pct);
  const labels = sorted.map((s) => cleanFeature(s.feature));
  const colors = sorted.map((s) =>
    s.direction === "increases risk" ? "#FF6B5A" : "#D6F84C"
  );

  return (
    <>
      <Plot
        data={[{
          type: "bar",
          orientation: "h",
          x: values,
          y: labels,
          marker: { color: colors, cornerradius: 6 },
          text: values.map((v) => `${v.toFixed(0)}%`),
          textposition: "outside",
          textfont: { color: text, family: "JetBrains Mono, monospace", size: 11 },
          hovertemplate: "%{y}<br>%{x:.1f}% of this prediction<extra></extra>",
        }]}
        layout={{
          height,
          margin: { t: 8, b: 24, l: 150, r: 44 },
          paper_bgcolor: "transparent",
          plot_bgcolor: "transparent",
          font: { color: text, family: "Inter, sans-serif", size: 11 },
          xaxis: { range: [0, Math.max(...values) * 1.3], gridcolor: grid, zeroline: false },
          yaxis: { automargin: true },
          bargap: 0.35,
          showlegend: false,
        }}
        config={{ displayModeBar: false, responsive: true }}
        style={{ width: "100%", height }}
        useResizeHandler
      />
      <div className="mt-1">
        <div className="flex items-center gap-4 justify-center text-[11px] t-muted">
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-danger" /> above model baseline
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-lime-400" /> below model baseline
          </span>
        </div>
        <p className="text-[10px] t-faint text-center mt-1.5">
          Explains the signature-risk component only, relative to the model's
          class-weighted baseline.
        </p>
      </div>
    </>
  );
}