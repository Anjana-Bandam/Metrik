/**
 * Builds a human-readable, print-ready HTML report for one machine.
 * Opening it triggers the browser print dialog, so "Save as PDF" produces
 * a proper PDF without pulling in a PDF library.
 */

const esc = (s) => String(s ?? "").replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const fmtDate = (iso) => {
  try {
    return new Date(iso).toLocaleString("en-IN",
      { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return iso;
  }
};

const RISK_LABEL = {
  green: "Healthy", yellow: "Monitor",
  red: "Action required", offline: "No signal",
};
const RISK_COLOR = {
  green: "#5c8a1f", yellow: "#a8760a",
  red: "#c2352a", offline: "#6b7280",
};

export function buildMachineReport(machine, plant) {
  const risk = machine.status;
  const offline = machine.state === "OFFLINE";

  const sensorRows = [
    ["Spindle speed", machine.sensors.spindle_speed.toFixed(0), "rpm"],
    ["Feed rate / load", machine.sensors.feed_rate.toFixed(1), "Nm"],
    ["Depth of cut", machine.sensors.depth_of_cut, "mm"],
    ["Cumulative tool runtime", machine.sensors.tool_runtime.toFixed(0), "min"],
    ["Surface cutting speed", machine.life.cutting_speed_m_min, "m/min"],
    ["Process temperature", machine.sensors.process_temperature.toFixed(1), "K"],
    ["Air temperature", machine.sensors.air_temperature.toFixed(1), "K"],
  ].map(([k, v, u]) =>
    '<tr><td>' + esc(k) + '</td><td class="num">' + esc(v) +
    ' <span class="u">' + esc(u) + '</span></td></tr>'
  ).join("");

  const shapRows = (machine.shap_values || []).slice(0, 6).map((s) => {
    const name = s.feature.replace(/\s*\[[^\]]*\]/, "");
    const up = s.direction === "increases risk";
    return '<tr><td>' + esc(name) + '</td>' +
      '<td class="num">' + s.contribution_pct.toFixed(1) + '%</td>' +
      '<td style="color:' + (up ? "#c2352a" : "#5c8a1f") + '">' +
      (up ? "above baseline" : "below baseline") + '</td>' +
      '<td><div class="bar"><span style="width:' +
      Math.min(s.contribution_pct * 2, 100) + '%;background:' +
      (up ? "#e0705f" : "#a9c94a") + '"></span></div></td></tr>';
  }).join("");

  const changeRows = (machine.tool_changes || []).slice(-6).reverse().map((t) =>
    '<tr><td>' + esc(fmtDate(t.logged_at)) + '</td>' +
    '<td class="num">' + t.runtime_at_change.toFixed(0) + ' min</td>' +
    '<td class="num">' + t.predicted_risk_at_change.toFixed(0) + '%</td>' +
    '<td>' + (t.was_actually_worn === null ? "not recorded"
      : t.was_actually_worn ? "confirmed worn" : "still serviceable") + '</td>' +
    '<td>' + esc(t.logged_by) + '</td></tr>'
  ).join("") ||
    '<tr><td colspan="5" class="muted">No tool changes logged yet.</td></tr>';

  const estimatedNote = (machine.estimated_fields && machine.estimated_fields.length)
    ? '<p class="muted" style="font-size:11.5px">Estimated (no direct sensor): ' +
      machine.estimated_fields.map((f) => esc(f.replace(/\s*\[[^\]]*\]/, ""))).join(", ") +
      '.</p>'
    : "";

  const overrideNote = machine.override.override_pct < 100
    ? '<br><span class="muted">Set the feed override dial on the control panel to ' +
      machine.override.override_pct + '%.</span>'
    : "";

  const riskSplit = (machine.ml_risk_pct !== undefined && !offline)
    ? '<h2>How this score was reached</h2><table><tbody>' +
      '<tr><td>Signature risk (XGBoost on live parameters)</td>' +
      '<td class="num">' + machine.ml_risk_pct.toFixed(1) + '%</td></tr>' +
      '<tr><td>Life-used risk (Taylor consumed tool life)</td>' +
      '<td class="num">' + machine.physics_risk_pct.toFixed(1) + '%</td></tr>' +
      '<tr><td><b>Combined wear probability</b></td>' +
      '<td class="num"><b>' + machine.risk_pct.toFixed(1) + '%</b></td></tr>' +
      '</tbody></table>' +
      '<p class="muted" style="font-size:11.5px">Combined with a noisy-OR: the ' +
      'tool is at risk if the live signature looks abnormal or it has exhausted ' +
      'its expected life. A worn tool often still cuts with a normal signature.</p>'
    : "";

  return '<!doctype html><html><head><meta charset="utf-8">' +
'<title>Metrik report - ' + esc(machine.name) + '</title>' +
'<style>' +
'@page { size: A4; margin: 16mm; }' +
'* { box-sizing: border-box; }' +
'body { font: 13px/1.55 -apple-system,Segoe UI,Roboto,sans-serif; color:#16181d;' +
'  margin:0; padding:24px; max-width:820px; }' +
'header { display:flex; justify-content:space-between; align-items:flex-start;' +
'  border-bottom:2px solid #16181d; padding-bottom:14px; margin-bottom:22px; }' +
'.brand { display:flex; align-items:center; gap:10px; }' +
'.tile { width:30px; height:30px; border-radius:7px; background:#D6F84C;' +
'  display:grid; place-items:center; }' +
'h1 { font-size:19px; margin:0; letter-spacing:-.3px; }' +
'h2 { font-size:13px; text-transform:uppercase; letter-spacing:.9px; color:#6b7280;' +
'  margin:26px 0 9px; }' +
'.meta { text-align:right; font-size:11px; color:#6b7280; line-height:1.6; }' +
'.verdict { border-left:4px solid ' + RISK_COLOR[risk] + '; background:#f7f7f2;' +
'  padding:14px 18px; border-radius:0 8px 8px 0; margin-bottom:8px; }' +
'.verdict .big { font-size:30px; font-weight:700; letter-spacing:-1px;' +
'  color:' + RISK_COLOR[risk] + '; }' +
'.grid { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:14px 0; }' +
'.stat { background:#f7f7f2; border-radius:8px; padding:11px 13px; }' +
'.stat b { display:block; font-size:17px; margin-top:3px; }' +
'.lbl { font-size:10px; text-transform:uppercase; letter-spacing:.7px; color:#6b7280; }' +
'table { width:100%; border-collapse:collapse; font-size:12.5px; }' +
'th { text-align:left; font-size:10px; text-transform:uppercase; letter-spacing:.7px;' +
'  color:#6b7280; border-bottom:1px solid #d8d7c8; padding:7px 8px; }' +
'td { padding:7px 8px; border-bottom:1px solid #ecebe2; }' +
'.num { font-variant-numeric:tabular-nums; font-weight:600; }' +
'.u { font-weight:400; color:#6b7280; font-size:10.5px; }' +
'.muted { color:#6b7280; }' +
'.bar { background:#ecebe2; height:7px; border-radius:4px; overflow:hidden; width:110px; }' +
'.bar span { display:block; height:100%; }' +
'.note { background:#f7f7f2; border-radius:8px; padding:13px 16px; font-size:12.5px; }' +
'footer { margin-top:30px; padding-top:12px; border-top:1px solid #d8d7c8;' +
'  font-size:10.5px; color:#6b7280; line-height:1.6; }' +
'@media print { body { padding:0; } .noprint { display:none; } }' +
'.noprint { position:fixed; top:14px; right:14px; }' +
'.noprint button { font:600 13px/1 inherit; padding:10px 18px; border:0; cursor:pointer;' +
'  border-radius:99px; background:#16181d; color:#fff; }' +
'</style></head><body>' +

'<div class="noprint"><button onclick="window.print()">Save as PDF</button></div>' +

'<header><div class="brand">' +
'<div class="tile"><svg width="18" height="18" viewBox="0 0 20 20" fill="none">' +
'<path d="M2 16.5 C6 16, 9 14, 11.5 9.5 S16 3.5, 18 3" stroke="#0E0F12"' +
' stroke-width="2.2" stroke-linecap="round" fill="none"/>' +
'<circle cx="11.5" cy="9.5" r="1.9" fill="#0E0F12"/></svg></div>' +
'<div><h1>Tool Wear Report</h1>' +
'<div class="muted" style="font-size:11.5px">' + esc(machine.name) + ' &middot; ' +
esc(machine.location) + '</div></div></div>' +
'<div class="meta"><b>' + esc(plant || "Metrik") + '</b><br>' +
'Generated ' + esc(fmtDate(new Date().toISOString())) + '<br>' +
'Data source: ' + esc(machine.source) + '</div></header>' +

'<div class="verdict"><div class="lbl">Wear probability</div>' +
'<div class="big">' + (offline ? "No signal" : machine.risk_pct.toFixed(0) + "%") + '</div>' +
'<div style="margin-top:5px"><b>' + RISK_LABEL[risk] + '</b>' +
(offline ? "" : ' &mdash; confidence range ' +
  Math.round(machine.life.remaining_low_min) + '&ndash;' +
  Math.round(machine.life.remaining_high_min) + ' min remaining') +
'</div></div>' +

'<div class="grid">' +
'<div class="stat"><span class="lbl">Est. life left</span><b>' +
(offline ? "&mdash;" : esc(machine.est_time_to_failure)) + '</b></div>' +
'<div class="stat"><span class="lbl">Life consumed</span><b>' +
(offline ? "&mdash;" : machine.life.life_consumed_pct.toFixed(0) + "%") + '</b></div>' +
'<div class="stat"><span class="lbl">Scrap exposure</span><b>' +
(offline ? "&mdash;" : "$" + machine.cost_impact.toFixed(0)) + '</b></div>' +
'<div class="stat"><span class="lbl">Machine state</span><b style="font-size:14px">' +
esc(machine.state_label) + '</b></div>' +
'</div>' +

'<h2>Recommended action</h2>' +
'<div class="note"><b>' + esc(machine.override.text) + '</b>' + overrideNote + '</div>' +

'<h2>Assessment</h2>' +
'<div class="note">' + esc(machine.narrative) + '</div>' +

riskSplit +

'<h2>What is driving this prediction</h2>' +
'<table><thead><tr><th>Parameter</th><th>Contribution</th>' +
'<th>Direction</th><th></th></tr></thead><tbody>' +
(shapRows || '<tr><td colspan="4" class="muted">No prediction to explain.</td></tr>') +
'</tbody></table>' +

'<h2>Sensor readout at time of report</h2>' +
'<table><tbody>' + sensorRows + '</tbody></table>' + estimatedNote +

'<h2>Tool change history</h2>' +
'<table><thead><tr><th>Logged</th><th>Runtime</th><th>Predicted</th>' +
'<th>Operator verdict</th><th>By</th></tr></thead><tbody>' +
changeRows + '</tbody></table>' +

'<footer><b>Metrik is a decision-support tool.</b> It does not start, stop or ' +
'reconfigure machinery. Wear probability combines an XGBoost classifier on live ' +
'machining parameters with a Taylor tool-life estimate (V&middot;T&#8319; = C) derived ' +
'from surface cutting speed, corrected for material hardness, depth of cut and ' +
'load. Figures are estimates with the stated confidence range and should be read ' +
'alongside operator judgement, not in place of it.</footer>' +

'<scr' + 'ipt>' +
'window.addEventListener("load", function () {' +
'  setTimeout(function () { window.print(); }, 350);' +
'});' +
'</scr' + 'ipt>' +

'</body></html>';
}

/**
 * Opens the report in a new tab. The auto-print script lives inside the
 * generated document, so the dialog fires on its own once layout settles.
 */
export function openMachineReport(machine, plant) {
  const html = buildMachineReport(machine, plant);
  const blob = new Blob([html], { type: "text/html" });
  const url = URL.createObjectURL(blob);

  const win = window.open(url, "_blank");
  if (!win) {
    URL.revokeObjectURL(url);
    alert(
      "Your browser blocked the report window.\n\n" +
      "Allow pop-ups for this site (look for the blocked-popup icon in the " +
      "address bar), then try again."
    );
    return;
  }

  setTimeout(() => URL.revokeObjectURL(url), 60000);
}