/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // --- Dark mode surfaces (flux charcoal) ---
        ink: {
          950: "#0E0F12",
          900: "#141519",
          800: "#1B1D22",
          700: "#24262D",
          600: "#2F323A",
          500: "#3D4149",
        },
        // --- Light mode surfaces (BizLink cream) ---
        cream: {
          50: "#FAFAF5",
          100: "#F2F1E8",
          200: "#E8E7DA",
          300: "#D8D7C8",
        },
        // --- Signature accent: flux lime ---
        lime: {
          200: "#EBFBA8",
          300: "#E2F97C",
          400: "#D6F84C",
          500: "#C2E834",
          600: "#A3C71F",
        },
        // --- Secondary: flux soft violet (used for data/secondary series) ---
        violet: {
          300: "#CFC0FB",
          400: "#B9A6F7",
          500: "#9F86F0",
        },
        // --- Status (distinct from brand lime so they never read as the same) ---
        ok: "#5FD68A",
        warn: "#FFC24B",
        danger: "#FF6B5A",
        offline: "#7A7F89",
      },
      fontFamily: {
        display: ["Poppins", "sans-serif"],
        body: ["Inter", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      borderRadius: {
        card: "20px",
        pill: "999px",
      },
      boxShadow: {
        card: "0 1px 2px rgba(16,18,22,0.04), 0 8px 24px rgba(16,18,22,0.06)",
        "card-dark": "0 1px 2px rgba(0,0,0,0.4), 0 8px 28px rgba(0,0,0,0.35)",
        lift: "0 12px 32px rgba(16,18,22,0.12)",
        "glow-lime": "0 0 0 1px rgba(214,248,76,0.35), 0 0 28px rgba(214,248,76,0.18)",
        "glow-danger": "0 0 0 1px rgba(255,107,90,0.45), 0 0 28px rgba(255,107,90,0.2)",
      },
      keyframes: {
        pulseDot: {
          "0%,100%": { opacity: 1, transform: "scale(1)" },
          "50%": { opacity: 0.5, transform: "scale(1.3)" },
        },
        rise: {
          "0%": { opacity: 0, transform: "translateY(8px)" },
          "100%": { opacity: 1, transform: "translateY(0)" },
        },
        sweep: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        "pulse-dot": "pulseDot 1.8s ease-in-out infinite",
        rise: "rise 0.4s cubic-bezier(0.16,1,0.3,1) both",
        sweep: "sweep 1.8s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};