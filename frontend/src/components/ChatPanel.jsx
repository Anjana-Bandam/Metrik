import React, { useState, useRef, useEffect } from "react";
import { Sparkles, Send, Loader2 } from "lucide-react";
import { api } from "../api.js";

const SUGGESTIONS = [
  "Why is this at risk?",
  "What should I do?",
  "When do I change the tool?",
  "How does the model work?",
];

export default function ChatPanel({ machineId, seedNarrative, compact }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef(null);
  const seededFor = useRef(null);

  // Seed ONCE per machine. Previously this re-ran on every 2s poll (the
  // narrative text contains the changing risk number), which wiped the
  // conversation about a second after every answer arrived.
  useEffect(() => {
    if (seededFor.current === machineId) return;
    seededFor.current = machineId;
    setMessages(seedNarrative ? [{ role: "assistant", text: seedNarrative }] : []);
  }, [machineId, seedNarrative]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages, busy]);

  const ask = async (question) => {
    const q = question.trim();
    if (!q || busy) return;
    setMessages((m) => [...m, { role: "user", text: q }]);
    setInput("");
    setBusy(true);
    try {
      const { answer } = await api.chat(q, machineId);
      setMessages((m) => [...m, { role: "assistant", text: answer }]);
    } catch (err) {
      setMessages((m) => [...m, {
        role: "assistant",
        text: `I couldn't reach the Metrik service just then (${err.message}). Try again?`,
      }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card flex flex-col overflow-hidden">
      <div className="flex items-center gap-2.5 px-4 py-3
                      border-b border-cream-300/70 dark:border-white/[0.07]">
        <div className="w-7 h-7 rounded-lg bg-lime-400 grid place-items-center text-ink-950 shrink-0">
          <Sparkles size={14} strokeWidth={2.4} />
        </div>
        <div>
          <p className="text-sm font-bold t-primary leading-tight">Metrik assistant</p>
          <p className="text-[11px] t-faint">Answers from this machine's live values</p>
        </div>
      </div>

      <div className={`flex-1 overflow-y-auto px-4 py-4 space-y-3 ${
        compact ? "max-h-[220px]" : "max-h-[300px] min-h-[180px]"}`}>
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "flex justify-end" : ""}>
            <p className={`text-sm leading-relaxed max-w-[92%] px-3.5 py-2.5 rounded-2xl ${
              m.role === "user"
                ? "bg-lime-400 text-ink-950 font-medium rounded-br-md"
                : "bg-cream-100 dark:bg-ink-700 t-secondary rounded-bl-md"
            }`}>
              {m.text}
            </p>
          </div>
        ))}
        {busy && (
          <div className="flex items-center gap-2 t-faint text-sm px-1">
            <Loader2 size={14} className="animate-spin" /> Thinking...
          </div>
        )}
        <div ref={endRef} />
      </div>

      {messages.length <= 1 && (
        <div className="px-4 pb-2 flex flex-wrap gap-1.5">
          {SUGGESTIONS.map((s) => (
            <button key={s} type="button" onClick={() => ask(s)}
              className="text-[11px] px-2.5 py-1.5 rounded-pill border
                         border-cream-300 dark:border-white/12 t-muted
                         hover:border-lime-400 hover:text-lime-600 dark:hover:text-lime-300
                         transition-colors">
              {s}
            </button>
          ))}
        </div>
      )}

      <div className="p-3 border-t border-cream-300/70 dark:border-white/[0.07] flex gap-2">
        <input value={input} onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); ask(input); } }}
          placeholder="Ask about this machine..."
          className="field py-2.5 text-sm" />
        <button type="button" onClick={() => ask(input)} disabled={!input.trim() || busy}
          className="btn-primary px-3.5 shrink-0" aria-label="Send">
          <Send size={15} />
        </button>
      </div>
    </div>
  );
}