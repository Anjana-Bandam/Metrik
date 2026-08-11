import React, { useEffect, useState, useCallback, useMemo } from "react";
import { Cpu, AlertTriangle, Clock3, PiggyBank, Download, Plus, ArrowRight } from "lucide-react";
import Header from "../components/Header.jsx";
import KpiCard from "../components/KpiCard.jsx";
import MachineGrid from "../components/MachineGrid.jsx";
import DetailModal from "../components/DetailModal.jsx";
import AddMachineModal from "../components/AddMachineModal.jsx";
import { api, downloadJson } from "../api.js";
import { useAuth } from "../auth.jsx";

const POLL_MS = 2000;

export default function DashboardPage() {
  const { user } = useAuth();
  const [machines, setMachines] = useState([]);
  const [kpis, setKpis] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [addOpen, setAddOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [query, setQuery] = useState("");
  const [error, setError] = useState(null);
  const [firstLoad, setFirstLoad] = useState(true);

  const poll = useCallback(() => {
    api.getAllMachines()
      .then((d) => { setMachines(d.machines); setKpis(d.kpis); setError(null); })
      .catch((e) => setError(e.message))
      .finally(() => setFirstLoad(false));
  }, []);

  useEffect(() => {
    poll();
    const id = setInterval(poll, POLL_MS);
    return () => clearInterval(id);
  }, [poll]);

  const selected = useMemo(
    () => machines.find((m) => m.machine_id === selectedId) || null,
    [machines, selectedId]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return machines;
    return machines.filter((m) =>
      m.name.toLowerCase().includes(q) || m.location.toLowerCase().includes(q));
  }, [machines, query]);

  // The "what needs me right now" queue — stops the dashboard feeling passive
  const needsAction = useMemo(
    () => machines
      .filter((m) => m.state === "RUNNING" && m.status !== "green")
      .sort((a, b) => b.risk_pct - a.risk_pct),
    [machines]);

  const handleCreate = async (payload) => {
    setCreating(true);
    try { await api.addMachine(payload); await poll(); setAddOpen(false); }
    catch (e) { setError(e.message); }
    finally { setCreating(false); }
  };

  return (
    <div className="flex-1 min-w-0">
      <Header
        title={`${user?.company}`}
        subtitle="Live fleet · refreshing every 2 seconds"
        onSearch={setQuery} searchValue={query}
        actions={
          <button onClick={() => downloadJson(api.exportDashboardUrl(), "metrik_dashboard_export.json")}
            className="btn-outline text-xs px-3.5 py-2 hidden sm:inline-flex">
            <Download size={14} /> Export
          </button>
        } />

      <div className="p-5 md:p-8 space-y-6">
        {error && (
          <div className="card p-4 text-sm text-danger border-danger/30">
            Couldn't reach the Metrik API ({error}). Is the FastAPI backend running on port 8000?
          </div>
        )}

        {/* KPIs */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <KpiCard icon={Cpu} label="Machines running" value={kpis?.active_machines ?? "—"}
            foot={kpis ? `${kpis.total_machines} connected · ${kpis.offline_machines} offline` : ""}
            tone="lime" />
          <KpiCard icon={AlertTriangle} label="Needs attention"
            value={kpis?.active_warnings ?? "—"}
            foot="running machines above 40% wear" tone="danger" />
          <KpiCard icon={Clock3} label="Avg. tool life left"
            value={kpis?.avg_remaining_life_hours ?? "—"} unit="hrs"
            foot="across running machines" tone="violet" />
          <KpiCard icon={PiggyBank} label="Scrap avoided" variant="invert"
            value={kpis ? `$${kpis.scrap_saved_usd.toLocaleString()}` : "—"}
            foot="from confirmed tool changes" tone="lime" />
        </div>

        {/* Action queue */}
        {needsAction.length > 0 && (
          <div className="card p-5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="font-display font-bold text-base t-primary">Needs your attention</h2>
                <p className="text-xs t-muted mt-0.5">
                  Highest risk first. Metrik recommends — you decide.
                </p>
              </div>
              <span className="chip chip-danger">{needsAction.length}</span>
            </div>
            <div className="space-y-2">
              {needsAction.slice(0, 4).map((m) => (
                <button key={m.machine_id} onClick={() => setSelectedId(m.machine_id)}
                  className="w-full flex items-center gap-3 p-3.5 rounded-2xl text-left
                             bg-cream-100 dark:bg-ink-800 hover:bg-cream-200 dark:hover:bg-ink-600
                             transition-colors group">
                  <span className={`status-dot ${m.status === "red" ? "bg-danger pulsing" : "bg-warn"}`} />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold t-primary truncate">{m.name}</p>
                    <p className="text-xs t-muted truncate">{m.override.text}</p>
                  </div>
                  <div className="text-right shrink-0 hidden sm:block">
                    <p className={`telemetry text-sm font-bold ${
                      m.status === "red" ? "text-danger" : "text-warn"}`}>
                      {m.risk_pct.toFixed(0)}%
                    </p>
                    <p className="text-[10px] t-faint">{m.est_time_to_failure} left</p>
                  </div>
                  <ArrowRight size={15}
                    className="t-faint group-hover:text-lime-600 dark:group-hover:text-lime-300 shrink-0" />
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Fleet */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display font-bold text-base t-primary">
              Fleet <span className="t-faint font-medium">({filtered.length})</span>
            </h2>
            <button onClick={() => setAddOpen(true)} className="btn-primary text-xs px-3.5 py-2">
              <Plus size={14} /> Add machine
            </button>
          </div>
          <MachineGrid machines={filtered} loading={firstLoad}
            onOpen={(m) => setSelectedId(m.machine_id)}
            onAddClick={() => setAddOpen(true)} />
        </div>
      </div>

      <DetailModal machine={selected} onClose={() => setSelectedId(null)} onRefresh={poll} />
      <AddMachineModal open={addOpen} onClose={() => setAddOpen(false)}
        onCreate={handleCreate} creating={creating} />
    </div>
  );
}