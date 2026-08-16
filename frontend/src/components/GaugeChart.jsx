import React from "react";
import Plot from "react-plotly.js";
import { useTheme } from "../theme.jsx";

const COLOR = { green: "#D6F84C", yellow: "#FFC24B", red: "#FF6B5A", offline: "#7A7F89" };
const FILL = {
  green:  (d) => (d ? "rgba(214,248,76,0.10)" : "rgba(214,248,76,0.22)"),
  yellow: (d) => (d ? "rgba(255,194,75,0.10)" : "rgba(255,194,75,0.20)"),
  red:    (d) => (d ? "rgba(255,107,90,0.12)" : "rgba(255,107,90,0.18)"),
};

/**
 * One gauge, two jobs.
 *
 * Metrik shows two very different quantities side by side — calibrated scrap
 * probability in %, and measured flank wear in mm — and they must read as the
 * same instrument so an operator can compare them at a glance. Everything that
 * differs between them (scale, unit, decimals, where the amber and red bands
 * start) is therefore a prop, and the thresholds come from the API rather than
 * being hardcoded here: they are model outputs and they move when the model is
 * retrained.
 */
export default function GaugeChart({
  value = 0,
  max = 100,
  suffix = "%",
  decimals = 0,
  watch = 40,
  alert = 70,
  band,
  height = 240,
  low,
  high,
}) {
  const { resolvedTheme } = useTheme();
  const dark = resolvedTheme === "dark";

  const resolvedBand = band || (value < watch ? "green" : value < alert ? "yellow" : "red");
  const color = COLOR[resolvedBand] || COLOR.green;
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
            suffix,
            valueformat: `.${decimals}f`,
            font: { family: "JetBrains Mono, monospace", size: 34, color: text },
          },
          gauge: {
            axis: {
              range: [0, max],
              tickwidth: 1,
              tickcolor: tick,
              tickfont: { color: tick, size: 10 },
              nticks: 5,
            },
            bar: { color, thickness: 0.3 },
            bgcolor: "transparent",
            borderwidth: 0,
            steps: [
              { range: [0, watch],      color: FILL.green(dark) },
              { range: [watch, alert],  color: FILL.yellow(dark) },
              { range: [alert, max],    color: FILL.red(dark) },
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
