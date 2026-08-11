import React from "react";

/**
 * Metrik mark: a tool-wear curve rising through a threshold line.
 * `size` scales the tile; `showWordmark` toggles the "Metrik" text.
 */
export default function Logo({ size = 32, showWordmark = true, inverted = false }) {
  return (
    <div className="flex items-center gap-2.5 select-none">
      <div
        className="rounded-[10px] bg-lime-400 grid place-items-center shrink-0"
        style={{ width: size, height: size }}
      >
        <svg width={size * 0.62} height={size * 0.62} viewBox="0 0 20 20" fill="none">
          {/* threshold line */}
          <path d="M2 6.5 H18" stroke="#0E0F12" strokeWidth="1.2"
                strokeDasharray="2 2" strokeLinecap="round" opacity=".45" />
          {/* wear curve rising through it */}
          <path d="M2 16.5 C6 16, 9 14, 11.5 9.5 S16 3.5, 18 3"
                stroke="#0E0F12" strokeWidth="2.2"
                strokeLinecap="round" fill="none" />
          {/* the moment it crosses */}
          <circle cx="11.5" cy="9.5" r="1.9" fill="#0E0F12" />
        </svg>
      </div>

      {showWordmark && (
        <span
          className={`font-display font-bold tracking-[-0.02em] ${
            inverted ? "text-white" : "t-primary"
          }`}
          style={{ fontSize: size * 0.56 }}
        >
          Metrik
        </span>
      )}
    </div>
  );
}