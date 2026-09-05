import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Loader2, Activity, Wrench, PowerOff } from "lucide-react";
import { useAuth } from "../auth.jsx";

/* Mini machine card — shows the actual product instead of a stock hero image */
function PreviewCard({ name, pct, tone, state, bay }) {
  const c = { ok: "#D6F84C", warn: "#FFC24B", bad: "#FF6B5A", off: "#7A7F89" }[tone];
  const Icon = state === "Offline" ? PowerOff : state === "Tool change" ? Wrench : Activity;
  return (
    <div className="bg-white rounded-2xl p-4 shadow-[0_8px_28px_rgba(0,0,0,0.28)]">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="min-w-0">
          <p className="font-semibold text-[13px] text-[#16181d] truncate">{name}</p>
          <p className="text-[11px] text-[#8a8f98]">{bay}</p>
        </div>
        <span className="inline-flex items-center gap-1 text-[10px] font-semibold
                         px-2 py-1 rounded-full bg-[#f2f1e8] text-[#5a616d] shrink-0">
          <Icon size={9} /> {state}
        </span>
      </div>
      <div className="flex items-end gap-1.5">
        <span className="text-[30px] font-bold leading-none tracking-tight"
              style={{ color: tone === "off" ? "#c3c6cb" : "#16181d",
                       fontFamily: "JetBrains Mono, monospace" }}>
          {pct === null ? "—" : pct}
        </span>
        {pct !== null && <span className="text-xs text-[#8a8f98] mb-0.5">% wear</span>}
      </div>
      <div className="h-1.5 rounded-full bg-[#eceade] mt-3 overflow-hidden">
        <div className="h-full rounded-full"
             style={{ width: `${pct ?? 0}%`, background: c }} />
      </div>
    </div>
  );
}

export default function LoginPage() {
  const { signIn, signUp } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState("signin");
  const [form, setForm] = useState({
    username: "", password: "", company: "", full_name: "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setError(""); setBusy(true);
    try {
      if (mode === "signin") await signIn(form.username, form.password);
      else await signUp(form);
      navigate("/", { replace: true });
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  };

  const useDemo = async () => {
    setError(""); setBusy(true);
    try {
      await signIn("demo", "metrik123");
      navigate("/", { replace: true });
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  };

  const inputCls = "w-full px-4 py-3 rounded-2xl text-sm bg-white border " +
    "border-[#e4e2d6] text-[#16181d] outline-none transition-colors " +
    "placeholder:text-[#b0b4bb] focus:border-[#C2E834] focus:ring-2 focus:ring-[#D6F84C]/30";
  const labelCls = "text-[11px] font-semibold uppercase tracking-[0.08em] text-[#8a8f98]";

  return (
    <div className="min-h-screen bg-[#f2f1e8] p-3 sm:p-5 lg:p-7">
      <div className="min-h-[calc(100vh-24px)] lg:min-h-[calc(100vh-56px)]
                      bg-[#16181d] rounded-[26px] lg:rounded-[34px] overflow-hidden
                      grid lg:grid-cols-[1.05fr_0.95fr]">

        {/* ---------- Left: product, not marketing ---------- */}
        <div className="hidden lg:flex flex-col justify-between p-10 xl:p-12 relative">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-[9px] bg-[#D6F84C] grid place-items-center">
              <svg width="19" height="19" viewBox="0 0 20 20" fill="none">
                <path d="M2 6.5 H18" stroke="#0E0F12" strokeWidth="1.2"
                      strokeDasharray="2 2" strokeLinecap="round" opacity=".45" />
                <path d="M2 16.5 C6 16, 9 14, 11.5 9.5 S16 3.5, 18 3"
                      stroke="#0E0F12" strokeWidth="2.2" strokeLinecap="round" fill="none" />
                <circle cx="11.5" cy="9.5" r="1.9" fill="#0E0F12" />
              </svg>
            </div>
            <span className="font-display font-bold text-[19px] text-white tracking-[-0.02em]">
              Metrik
            </span>
          </div>

          <div className="my-10">
            <h1 className="font-display font-bold text-white text-[38px] xl:text-[44px]
                           leading-[1.06] tracking-[-0.035em]">
              Change the tool
              <br />
              <span className="text-[#D6F84C]">before it scraps</span>
              <br />
              the part.
            </h1>
            <p className="mt-5 text-[#c9ccd2]/65 text-[15px] leading-relaxed max-w-[400px]">
              Metrik reads live spindle telemetry, scores tool wear with a
              confidence range, and tells your operator which parameter is
              driving it — so tools get changed on evidence, not on a calendar.
            </p>
          </div>

          {/* Live-looking fleet preview */}
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.1em]
                          text-[#c9ccd2]/40 mb-3">
              Your fleet, at a glance
            </p>
            <div className="grid grid-cols-3 gap-3 max-w-[520px]">
              <PreviewCard name="VMC-03 DMG Mori" bay="Bay 2" pct={78} tone="bad" state="Running" />
              <PreviewCard name="VMC-01 Haas VF2" bay="Bay 1" pct={21} tone="ok" state="Running" />
              <PreviewCard name="VMC-06 Jyoti" bay="Bay 3" pct={null} tone="off" state="Offline" />
            </div>

            <div className="flex flex-wrap gap-x-7 gap-y-2 mt-8 pt-6
                            border-t border-white/[0.08]">
              {[
                ["Taylor V·Tⁿ = C", "physics-backed life"],
                ["SHAP", "per-prediction drivers"],
                ["No control path", "decision support only"],
              ].map(([a, b]) => (
                <div key={b}>
                  <p className="text-[#D6F84C] font-semibold text-[13px]">{a}</p>
                  <p className="text-[11px] text-[#c9ccd2]/45 mt-0.5">{b}</p>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ---------- Right: the form, on cream ---------- */}
        <div className="bg-[#f7f6ef] lg:m-3 lg:rounded-[26px] flex items-center
                        justify-center p-7 sm:p-10">
          <form onSubmit={submit} className="w-full max-w-[350px]">

            {/* mobile logo */}
            <div className="lg:hidden flex items-center gap-2.5 mb-8">
              <div className="w-8 h-8 rounded-[9px] bg-[#D6F84C] grid place-items-center">
                <svg width="19" height="19" viewBox="0 0 20 20" fill="none">
                  <path d="M2 16.5 C6 16, 9 14, 11.5 9.5 S16 3.5, 18 3"
                        stroke="#0E0F12" strokeWidth="2.2" strokeLinecap="round" fill="none" />
                  <circle cx="11.5" cy="9.5" r="1.9" fill="#0E0F12" />
                </svg>
              </div>
              <span className="font-display font-bold text-[19px] text-[#16181d]">Metrik</span>
            </div>

            {/* segmented toggle */}
            <div className="flex p-1 rounded-full bg-[#e9e7db] mb-7">
              {[["signin", "Sign in"], ["signup", "Create account"]].map(([m, l]) => (
                <button key={m} type="button"
                  onClick={() => { setMode(m); setError(""); }}
                  className={`flex-1 py-2.5 rounded-full text-[13px] font-semibold transition-all ${
                    mode === m ? "bg-[#16181d] text-white shadow-sm" : "text-[#6b7280]"
                  }`}>{l}</button>
              ))}
            </div>

            <h2 className="font-display font-bold text-[26px] text-[#16181d] tracking-[-0.03em]
                           leading-tight">
              {mode === "signin" ? "Welcome back" : "Set up your plant"}
            </h2>
            <p className="text-[#6b7280] text-[13.5px] mt-1.5 mb-6">
              {mode === "signin"
                ? "Your machines and history stay scoped to this account."
                : "You'll start with a demo fleet you can edit or replace."}
            </p>

            {mode === "signup" && (
              <>
                <label className={labelCls}>Company / plant name</label>
                <input className={`${inputCls} mt-1.5 mb-4`} placeholder="Vasavi Precision Works"
                       value={form.company} onChange={set("company")} required />

                <label className={labelCls}>Your name</label>
                <input className={`${inputCls} mt-1.5 mb-4`} placeholder="Anjana"
                       value={form.full_name} onChange={set("full_name")} />

                <p className="text-[11px] text-[#9aa0a8] -mt-1 mb-4">
                  This is a public hackathon demo — please use a throwaway
                  password, not one you use elsewhere.
                </p>
              </>
            )}

            <label className={labelCls}>Username</label>
            <input className={`${inputCls} mt-1.5 mb-4`} placeholder="demo"
                   autoComplete="username" value={form.username}
                   onChange={set("username")} required />

            <label className={labelCls}>Password</label>
            <input className={`${inputCls} mt-1.5`} type="password" placeholder="••••••••"
                   autoComplete={mode === "signin" ? "current-password" : "new-password"}
                   value={form.password} onChange={set("password")} required />

            {error && (
              <p className="mt-4 text-[13px] text-[#c2352a] bg-[#ffe9e6] rounded-2xl px-4 py-3">
                {error}
              </p>
            )}

            <button type="submit" disabled={busy}
              className="w-full mt-6 py-3.5 rounded-full bg-[#16181d] text-white
                         text-sm font-semibold inline-flex items-center justify-center gap-2
                         hover:bg-[#24262d] transition-colors disabled:opacity-45">
              {busy ? <Loader2 size={16} className="animate-spin" />
                    : <>{mode === "signin" ? "Sign in" : "Create account"} <ArrowRight size={16} /></>}
            </button>

            {mode === "signin" && (
              <>
                <div className="flex items-center gap-3 my-5">
                  <span className="h-px flex-1 bg-[#dedbcd]" />
                  <span className="text-[11px] text-[#9aa0a8]">or</span>
                  <span className="h-px flex-1 bg-[#dedbcd]" />
                </div>
                <button type="button" onClick={useDemo} disabled={busy}
                  className="w-full py-3.5 rounded-full bg-[#D6F84C] text-[#16181d]
                             text-sm font-semibold hover:bg-[#E2F97C] transition-colors
                             disabled:opacity-45">
                  Explore the demo plant
                </button>
                <p className="text-center text-[11px] text-[#9aa0a8] mt-3.5">
                  demo · metrik123 — six machines, mixed states
                </p>
              </>
            )}
          </form>
        </div>
      </div>
    </div>
  );
}