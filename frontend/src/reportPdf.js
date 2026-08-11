/**
 * Builds a real PDF client-side with jsPDF and saves it straight to the
 * user's Downloads folder - no print dialog, no new tab.
 *
 * Drawn as vector text rather than a canvas screenshot, so the output stays
 * crisp at any zoom, the text is selectable and searchable, and the file is
 * ~30KB instead of a couple of megabytes.
 */
import { jsPDF } from "jspdf";

const INK = [22, 24, 29];
const MUTED = [107, 114, 128];
const LINE = [216, 215, 200];
const PANEL = [247, 247, 242];
const LIME = [214, 248, 76];

const RISK_RGB = {
  green: [92, 138, 31],
  yellow: [168, 118, 10],
  red: [194, 53, 42],
  offline: [107, 114, 128],
};
const RISK_LABEL = {
  green: "Healthy", yellow: "Monitor",
  red: "Action required", offline: "No signal",
};

const stripUnits = (s) => String(s).replace(/\s*\[[^\]]*\]/, "");

const fmtDate = (iso) => {
  try {
    return new Date(iso).toLocaleString("en-IN",
      { dateStyle: "medium", timeStyle: "short" });
  } catch { return String(iso); }
};

export function downloadMachinePdf(machine, plant) {
  const doc = new jsPDF({ unit: "mm", format: "a4" });
  const W = 210;
  const M = 16;            // page margin
  const CW = W - M * 2;    // content width
  let y = M;

  const offline = machine.state === "OFFLINE";
  const risk = machine.status;
  const riskColor = RISK_RGB[risk] || RISK_RGB.green;

  // --- helpers ------------------------------------------------------------
  const setFont = (size, style = "normal", color = INK) => {
    doc.setFont("helvetica", style);
    doc.setFontSize(size);
    doc.setTextColor(...color);
  };

  const pageBreak = (needed = 20) => {
    if (y + needed > 285) { doc.addPage(); y = M; }
  };

  const sectionTitle = (text) => {
    pageBreak(16);
    y += 7;
    setFont(8.5, "bold", MUTED);
    doc.text(text.toUpperCase(), M, y);
    y += 4;
    doc.setDrawColor(...LINE);
    doc.setLineWidth(0.2);
    doc.line(M, y, M + CW, y);
    y += 5;
  };

  /** Wrapped paragraph inside a soft panel. */
  const panel = (text, bold = false) => {
    const lines = doc.splitTextToSize(text, CW - 10);
    const h = lines.length * 4.6 + 8;
    pageBreak(h);
    doc.setFillColor(...PANEL);
    doc.roundedRect(M, y, CW, h, 2, 2, "F");
    setFont(9.5, bold ? "bold" : "normal", INK);
    doc.text(lines, M + 5, y + 6);
    y += h + 2;
  };

  /** Simple 2-or-more column table. */
  const table = (headers, rows, widths) => {
    pageBreak(14);
    if (headers) {
      setFont(7.5, "bold", MUTED);
      let x = M;
      headers.forEach((h, i) => { doc.text(h.toUpperCase(), x, y); x += widths[i]; });
      y += 2;
      doc.setDrawColor(...LINE);
      doc.line(M, y, M + CW, y);
      y += 4.5;
    }
    rows.forEach((row) => {
      pageBreak(8);
      let x = M;
      row.forEach((cell, i) => {
        const isObj = typeof cell === "object" && cell !== null;
        const txt = isObj ? cell.text : cell;
        setFont(9, isObj && cell.bold ? "bold" : "normal", isObj && cell.color ? cell.color : INK);
        doc.text(String(txt), x, y);
        x += widths[i];
      });
      y += 3.2;
      doc.setDrawColor(236, 235, 226);
      doc.line(M, y, M + CW, y);
      y += 4.5;
    });
  };

  // --- header -------------------------------------------------------------
  doc.setFillColor(...LIME);
  doc.roundedRect(M, y, 9, 9, 2, 2, "F");
  doc.setDrawColor(...INK);
  doc.setLineWidth(0.9);
  doc.lines([[1.6, -0.3], [1.6, -1.4], [1.9, -3.2]], M + 1.9, y + 6.8);  // wear curve
  doc.setFillColor(...INK);
  doc.circle(M + 5.1, y + 5.1, 0.85, "F");

  setFont(15, "bold", INK);
  doc.text("Tool Wear Report", M + 12, y + 5);
  setFont(8.5, "normal", MUTED);
  doc.text(`${machine.name}  |  ${machine.location}`, M + 12, y + 9);

  setFont(8.5, "bold", INK);
  doc.text(plant || "Metrik", M + CW, y + 3, { align: "right" });
  setFont(7.5, "normal", MUTED);
  doc.text(`Generated ${fmtDate(new Date().toISOString())}`, M + CW, y + 6.8, { align: "right" });
  doc.text(`Data source: ${machine.source}`, M + CW, y + 10, { align: "right" });

  y += 13;
  doc.setDrawColor(...INK);
  doc.setLineWidth(0.6);
  doc.line(M, y, M + CW, y);
  y += 8;

  // --- headline verdict ---------------------------------------------------
  const vh = 26;
  doc.setFillColor(...PANEL);
  doc.roundedRect(M, y, CW, vh, 2, 2, "F");
  doc.setFillColor(...riskColor);
  doc.rect(M, y, 1.4, vh, "F");

  setFont(7.5, "bold", MUTED);
  doc.text("WEAR PROBABILITY", M + 6, y + 6.5);
  setFont(22, "bold", riskColor);
  doc.text(offline ? "No signal" : `${machine.risk_pct.toFixed(0)}%`, M + 6, y + 16);
  setFont(9, "bold", INK);
  const band = offline ? "" :
    `  -  confidence range ${Math.round(machine.life.remaining_low_min)}-${Math.round(machine.life.remaining_high_min)} min remaining`;
  doc.text(RISK_LABEL[risk], M + 6, y + 22);
  setFont(9, "normal", MUTED);
  doc.text(band, M + 6 + doc.getTextWidth(RISK_LABEL[risk]), y + 22);
  y += vh + 5;

  // --- stat strip ---------------------------------------------------------
  const stats = [
    ["Est. life left", offline ? "-" : machine.est_time_to_failure],
    ["Life consumed", offline ? "-" : `${machine.life.life_consumed_pct.toFixed(0)}%`],
    ["Scrap exposure", offline ? "-" : `$${machine.cost_impact.toFixed(0)}`],
    ["Machine state", machine.state_label.split(" - ")[0]],
  ];
  const sw = (CW - 9) / 4;
  stats.forEach(([label, val], i) => {
    const x = M + i * (sw + 3);
    doc.setFillColor(...PANEL);
    doc.roundedRect(x, y, sw, 16, 2, 2, "F");
    setFont(6.8, "bold", MUTED);
    doc.text(label.toUpperCase(), x + 3.5, y + 5.5);
    setFont(11.5, "bold", INK);
    doc.text(String(val), x + 3.5, y + 12);
  });
  y += 21;

  // --- recommended action -------------------------------------------------
  sectionTitle("Recommended action");
  let action = machine.override.text;
  if (machine.override.override_pct < 100) {
    action += `  Set the feed override dial on the control panel to ${machine.override.override_pct}%.`;
  }
  panel(action, true);

  // --- assessment ---------------------------------------------------------
  sectionTitle("Assessment");
  panel(machine.narrative);

  // --- risk decomposition -------------------------------------------------
  if (machine.ml_risk_pct !== undefined && !offline) {
    sectionTitle("How this score was reached");
    table(null, [
      ["Signature risk (XGBoost on live parameters)", `${machine.ml_risk_pct.toFixed(1)}%`],
      ["Life-used risk (Taylor consumed tool life)", `${machine.physics_risk_pct.toFixed(1)}%`],
      [{ text: "Combined wear probability", bold: true },
       { text: `${machine.risk_pct.toFixed(1)}%`, bold: true }],
    ], [140, 38]);
    setFont(7.5, "normal", MUTED);
    const note = doc.splitTextToSize(
      "Combined with a noisy-OR: the tool is at risk if the live signature looks " +
      "abnormal or it has exhausted its expected life. A worn tool often still cuts " +
      "with a normal signature right up until it fails.", CW);
    doc.text(note, M, y);
    y += note.length * 3.4 + 2;
  }

  // --- SHAP ---------------------------------------------------------------
  sectionTitle("What is driving this prediction");
  const shapRows = (machine.shap_values || []).slice(0, 6).map((s) => {
    const up = s.direction === "increases risk";
    return [
      stripUnits(s.feature),
      `${s.contribution_pct.toFixed(1)}%`,
      { text: up ? "above baseline" : "below baseline",
        color: up ? [194, 53, 42] : [92, 138, 31] },
    ];
  });
  table(["Parameter", "Contribution", "Direction"],
        shapRows.length ? shapRows : [["No prediction to explain.", "", ""]],
        [88, 42, 48]);

  // --- sensors ------------------------------------------------------------
  sectionTitle("Sensor readout at time of report");
  table(null, [
    ["Spindle speed", `${machine.sensors.spindle_speed.toFixed(0)} rpm`],
    ["Feed rate / load", `${machine.sensors.feed_rate.toFixed(1)} Nm`],
    ["Depth of cut", `${machine.sensors.depth_of_cut} mm`],
    ["Cumulative tool runtime", `${machine.sensors.tool_runtime.toFixed(0)} min`],
    ["Surface cutting speed", `${machine.life.cutting_speed_m_min} m/min`],
    ["Process temperature", `${machine.sensors.process_temperature.toFixed(1)} K`],
    ["Air temperature", `${machine.sensors.air_temperature.toFixed(1)} K`],
  ], [110, 68]);

  if (machine.estimated_fields?.length) {
    setFont(7.5, "normal", MUTED);
    doc.text("Estimated (no direct sensor): " +
      machine.estimated_fields.map(stripUnits).join(", "), M, y);
    y += 5;
  }

  // --- tool changes -------------------------------------------------------
  sectionTitle("Tool change history");
  const tc = (machine.tool_changes || []).slice(-6).reverse();
  table(["Logged", "Runtime", "Predicted", "Verdict"],
    tc.length ? tc.map((t) => [
      fmtDate(t.logged_at),
      `${t.runtime_at_change.toFixed(0)} min`,
      `${t.predicted_risk_at_change.toFixed(0)}%`,
      t.was_actually_worn === null ? "not recorded"
        : t.was_actually_worn ? "confirmed worn" : "still serviceable",
    ]) : [["No tool changes logged yet.", "", "", ""]],
    [58, 30, 30, 60]);

  // --- footer on every page ----------------------------------------------
  const pages = doc.getNumberOfPages();
  for (let p = 1; p <= pages; p++) {
    doc.setPage(p);
    doc.setDrawColor(...LINE);
    doc.setLineWidth(0.2);
    doc.line(M, 283, M + CW, 283);
    setFont(6.6, "normal", MUTED);
    const foot = doc.splitTextToSize(
      "Metrik is a decision-support tool. It does not start, stop or reconfigure " +
      "machinery. Wear probability combines an XGBoost classifier on live machining " +
      "parameters with a Taylor tool-life estimate (V.T^n = C) derived from surface " +
      "cutting speed, corrected for material hardness, depth of cut and load. Figures " +
      "are estimates with the stated confidence range and should be read alongside " +
      "operator judgement, not in place of it.", CW - 22);
    doc.text(foot, M, 287);
    doc.text(`${p} / ${pages}`, M + CW, 287, { align: "right" });
  }

  const safe = machine.name.replace(/[^a-z0-9]+/gi, "_").toLowerCase();
  const stamp = new Date().toISOString().slice(0, 10);
  doc.save(`metrik_${safe}_${stamp}.pdf`);
}