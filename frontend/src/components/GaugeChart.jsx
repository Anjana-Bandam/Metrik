import React from "react";
import Plot from "react-plotly.js";
import { useTheme } from "../theme.jsx";

const COLOR = { green: "#D6F84C", yellow: "#FFC24B", red: "#FF6B5A", offline: "#7A7F89" };

function bandFor(pct) {
  if (pct < 40) return "green";
  if (pct < 70) return "yellow";
  return "red";
}

export default function GaugeChart({ value = 0, height = 240, band, low, high }) {
  const { resolvedTheme } = useTheme();
  const dark = resolvedTheme === "dark";
  const color = COLOR[band || bandFor(value)];
  const text = dark ? "#FFFFFF" : "#141519";
  const tick = dark ? "rgba(242,241,232,0.45)" : "rgba(20,21,25,0.45)";

  return (
    <div className="relative">
      <Plot
        data={[{
          type: "indicator",
          mode: "gauge+number",
          value,
          number: {
            suffix: "%",
            font: { family: "JetBrains Mono, monospace", size: 38, color: text },
          },
          gauge: {
            axis: { range: [0, 100], tickwidth: 1, tickcolor: tick,
                    tickfont: { color: tick, size: 10 } },
            bar: { color, thickness: 0.3 },
            bgcolor: "transparent",
            borderwidth: 0,
            steps: [
              { range: [0, 40],  color: dark ? "rgba(214,248,76,0.10)" : "rgba(214,248,76,0.22)" },
              { range: [40, 70], color: dark ? "rgba(255,194,75,0.10)" : "rgba(255,194,75,0.20)" },
              { range: [70, 100],color: dark ? "rgba(255,107,90,0.12)" : "rgba(255,107,90,0.18)" },
            ],
            threshold: { line: { color, width: 4 }, thickness: 0.9, value },
          },
        }]}
        layout={{
          height,
          margin: { t: 24, b: 4, l: 28, r: 28 },
          paper_bgcolor: "transparent",
          font: { color: text },
          autosize: true,
        }}
        config={{ displayModeBar: false, responsive: true }}
        style={{ width: "100%", height }}
        useResizeHandler
      />
      {/* Confidence range — the problem statement requires we show uncertainty */}
      {low !== undefined && (
        <p className="text-center text-xs t-muted -mt-2">
          Confidence range{" "}
          <span className="telemetry t-secondary font-semibold">{low} – {high}</span>
        </p>
      )}
    </div>
  );
}