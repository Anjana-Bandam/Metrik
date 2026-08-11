import React, { createContext, useContext, useEffect, useState, useCallback } from "react";

const ThemeContext = createContext(null);

const STORAGE_KEY = "metrik-theme"; // 'dark' | 'light' | 'system'

function resolveSystemPref() {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyResolvedTheme(mode) {
  const resolved = mode === "system" ? resolveSystemPref() : mode;
  const root = document.documentElement;
  root.classList.remove("dark", "light");
  root.classList.add(resolved);
  return resolved;
}

export function ThemeProvider({ children }) {
  const [mode, setMode] = useState(() => localStorage.getItem(STORAGE_KEY) || "dark");
  const [resolvedTheme, setResolvedTheme] = useState("dark");

  useEffect(() => {
    setResolvedTheme(applyResolvedTheme(mode));
    localStorage.setItem(STORAGE_KEY, mode);
  }, [mode]);

  useEffect(() => {
    if (mode !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => setResolvedTheme(applyResolvedTheme("system"));
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [mode]);

  const cycleMode = useCallback((next) => setMode(next), []);

  return (
    <ThemeContext.Provider value={{ mode, resolvedTheme, setMode: cycleMode }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
