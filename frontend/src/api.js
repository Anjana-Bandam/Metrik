// Thin fetch wrapper. Every call attaches the session token, so the backend
// scopes the response to the logged-in plant account.
//
// In dev, Vite proxies "/api" to the local FastAPI server (see vite.config.js).
// In production the frontend and backend are typically separate deployments
// (e.g. Vercel + Render), so VITE_API_BASE must be set at build time to the
// deployed backend's full URL (e.g. https://metrik-api.onrender.com/api).
const BASE = import.meta.env.VITE_API_BASE || "/api";
const TOKEN_KEY = "metrik-token";

function authHeaders() {
  const token = localStorage.getItem(TOKEN_KEY);
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...authHeaders() },
    ...options,
  });
  if (res.status === 401) {
    localStorage.removeItem(TOKEN_KEY);
    window.location.reload();
    throw new Error("Session expired.");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${res.status})`);
  }
  return res.json();
}

export const api = {
  getAllMachines: () => request("/get_all_machines"),
  getMachine: (id) => request(`/machine/${id}`),

  predict: (payload) =>
    request("/predict", { method: "POST", body: JSON.stringify(payload) }),

  addMachine: (payload) =>
    request("/add_machine", { method: "POST", body: JSON.stringify(payload) }),

  setState: (id, state) =>
    request(`/machine/${id}/state`, {
      method: "POST",
      body: JSON.stringify({ state }),
    }),

  removeMachine: (id) => request(`/machine/${id}`, { method: "DELETE" }),

  logToolChange: (id, wasWorn, note) =>
    request(`/machine/${id}/tool_change`, {
      method: "POST",
      body: JSON.stringify({ was_actually_worn: wasWorn, note }),
    }),

  acknowledge: (id, decision, reason) =>
    request(`/machine/${id}/acknowledge`, {
      method: "POST",
      body: JSON.stringify({ decision, reason }),
    }),

  modelFeedback: () => request("/model_feedback"),

  chat: (question, machineId, history) =>
    request("/chat", {
      method: "POST",
      body: JSON.stringify({ question, machine_id: machineId || null, history: history || null }),
    }),

  exportMachineUrl: (id) => `${BASE}/export/machine/${id}`,
  exportDashboardUrl: () => `${BASE}/export/dashboard`,


  predictCsv: async (file) => {
    const fd = new FormData();
    fd.append("file", file);
    const token = localStorage.getItem(TOKEN_KEY);
    const res = await fetch("/api/predict_csv", {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: fd,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `CSV prediction failed (${res.status})`);
    }
    return res.json();
  },



   setFastMode: (id, enabled) =>
    request(`/machine/${id}/fast_mode`, {
      method: "POST",
      body: JSON.stringify({ enabled }),
    }),
};

/** Downloads a JSON export. Needs the auth header, so we fetch then blob it. */
export async function downloadJson(url, filename) {
  const res = await fetch(url, { headers: authHeaders() });
  const blob = await res.blob();
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(link.href);
}

// Shared display helpers ----------------------------------------------------
export const STATE_STYLE = {
  RUNNING:     { dot: "bg-ok",      chip: "chip-ok",      label: "Running" },
  IDLE:        { dot: "bg-warn",    chip: "chip-warn",    label: "Idle" },
  TOOL_CHANGE: { dot: "bg-violet-400", chip: "chip-neutral", label: "Tool change" },
  OFFLINE:     { dot: "bg-offline", chip: "chip-offline", label: "Offline" },
};

export const RISK_STYLE = {
  green:   { chip: "chip-ok",      dot: "bg-ok",      text: "text-ok",      label: "Healthy" },
  yellow:  { chip: "chip-warn",    dot: "bg-warn",    text: "text-warn",    label: "Monitor" },
  red:     { chip: "chip-danger",  dot: "bg-danger",  text: "text-danger",  label: "Act now" },
  offline: { chip: "chip-offline", dot: "bg-offline", text: "text-offline", label: "No signal" },
};

export const cleanFeature = (f) => f.replace(/\s*\[[^\]]*\]/, "");