import React from "react";
import { Search, Bell } from "lucide-react";
import ThemeToggle from "./ThemeToggle.jsx";
import { useAuth } from "../auth.jsx";

export default function Header({ title, subtitle, onSearch, searchValue, actions }) {
  const { user } = useAuth();

  return (
    <header className="sticky top-0 z-30 flex items-center gap-4 h-[72px] px-5 md:px-8
                       backdrop-blur-xl bg-cream-100/85 dark:bg-ink-950/85
                       border-b border-cream-300/70 dark:border-white/[0.07]">
      <div className="min-w-0 mr-auto">
        <h1 className="font-display font-bold text-xl t-primary tracking-[-0.02em] truncate">
          {title}
        </h1>
        {subtitle && <p className="text-xs t-muted truncate mt-0.5">{subtitle}</p>}
      </div>

      {onSearch && (
        <div className="hidden lg:flex items-center gap-2 w-60 px-4 py-2 rounded-pill
                        bg-white dark:bg-ink-800 border border-cream-300 dark:border-white/[0.08]">
          <Search size={15} className="t-faint shrink-0" />
          <input value={searchValue} onChange={(e) => onSearch(e.target.value)}
            placeholder="Search machines..."
          className="bg-transparent outline-none text-sm w-full t-primary
           placeholder:text-ink-500/60 dark:placeholder:text-cream-200/40" />
        </div>
      )}

      {actions}

      <button aria-label="Notifications"
        className="relative w-10 h-10 grid place-items-center rounded-pill t-secondary
                   hover:bg-white dark:hover:bg-ink-800 transition-colors">
        <Bell size={17} />
        <span className="absolute top-2.5 right-2.5 w-1.5 h-1.5 rounded-full bg-danger" />
      </button>

      <ThemeToggle />

      <div className="w-10 h-10 rounded-pill bg-ink-900 dark:bg-lime-400 grid place-items-center
                      text-lime-400 dark:text-ink-950 font-display font-bold text-xs shrink-0">
        {(user?.full_name || "?").slice(0, 2).toUpperCase()}
      </div>
    </header>
  );
}