import React from "react";
import { Moon, Sun, Monitor } from "lucide-react";
import { useTheme } from "../theme.jsx";

const OPTIONS = [
  { value: "light", icon: Sun, label: "Light" },
  { value: "dark", icon: Moon, label: "Dark" },
  { value: "system", icon: Monitor, label: "System" },
];

export default function ThemeToggle() {
  const { mode, setMode } = useTheme();
  return (
    <div role="radiogroup" aria-label="Theme"
         className="flex items-center gap-0.5 p-1 rounded-pill bg-cream-200 dark:bg-ink-700">
      {OPTIONS.map(({ value, icon: Icon, label }) => {
        const active = mode === value;
        return (
          <button key={value} role="radio" aria-checked={active} title={label}
            onClick={() => setMode(value)}
            className={`grid place-items-center w-7 h-7 rounded-pill transition-all ${
              active
                ? "bg-lime-400 text-ink-950"
                : "t-muted hover:text-lime-600 dark:hover:text-lime-300"
            }`}>
            <Icon size={13} strokeWidth={2.4} />
          </button>
        );
      })}
    </div>
  );
}