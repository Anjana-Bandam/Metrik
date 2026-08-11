import React from "react";
import { NavLink } from "react-router-dom";
import { LayoutGrid, SlidersHorizontal, FileText, Settings, LogOut, ShieldCheck } from "lucide-react";
import Logo from "./Logo.jsx";
import { useAuth } from "../auth.jsx";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutGrid, end: true },
  { to: "/simulation", label: "Job planner", icon: SlidersHorizontal },
  { to: "/reports", label: "Reports", icon: FileText },
  { to: "/settings", label: "Settings", icon: Settings },
];

export default function Sidebar() {
  const { user, signOut } = useAuth();

  return (
    <aside className="hidden md:flex flex-col w-[248px] shrink-0 sidebar-surface h-screen sticky top-0">
      <div className="px-6 h-[72px] flex items-center">
        <Logo size={30} inverted />
      </div>

      <nav className="flex-1 px-3 mt-3 space-y-1">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end}
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-3 rounded-2xl text-sm font-semibold transition-all ${
                isActive
                  ? "bg-lime-400 text-ink-950"
                  : "text-cream-200/60 hover:text-cream-50 hover:bg-white/[0.05]"
              }`
            }>
            <Icon size={17} strokeWidth={2.1} />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Guardrail card — restates the constraint the problem statement asks for */}
      <div className="mx-3 mb-3 p-4 rounded-card bg-white/[0.04] border border-white/[0.07]">
        <div className="flex items-center gap-2 text-lime-400 mb-2">
          <ShieldCheck size={15} />
          <span className="text-xs font-bold uppercase tracking-wide">Decision support</span>
        </div>
        <p className="text-[11px] leading-relaxed text-cream-200/50">
          Metrik never starts, stops or reconfigures a machine. Every
          recommendation is actioned by a person on the floor.
        </p>
      </div>

      <div className="mx-3 mb-4 p-3 rounded-card bg-white/[0.04] flex items-center gap-3">
        <div className="w-9 h-9 rounded-full bg-lime-400 grid place-items-center text-ink-950 font-display font-bold text-xs shrink-0">
          {(user?.full_name || user?.username || "?").slice(0, 2).toUpperCase()}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold text-cream-50 truncate">{user?.company}</p>
          <p className="text-[11px] text-cream-200/45 capitalize truncate">{user?.role}</p>
        </div>
        <button onClick={signOut} title="Sign out"
          className="w-8 h-8 grid place-items-center rounded-full text-cream-200/50 hover:text-danger hover:bg-white/[0.06]">
          <LogOut size={15} />
        </button>
      </div>
    </aside>
  );
}