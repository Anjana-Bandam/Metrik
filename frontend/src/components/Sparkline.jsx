import React from "react";

/** Tiny inline risk-trend line for machine cards. */
export default function Sparkline({ data = [], color = "#D6F84C", height = 32 }) {
  if (data.length < 2) {
    return <div style={{ height }} className="w-full" />;
  }
  const w = 100, h = height;
  const min = Math.min(...data), max = Math.max(...data);
  const span = max - min || 1;
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((v - min) / span) * (h - 4) - 2;
    return `${x},${y}`;
  });

  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none"
         style={{ height }} className="w-full overflow-visible">
      <polyline points={`0,${h} ${pts.join(" ")} ${w},${h}`}
        fill={color} opacity="0.12" stroke="none" />
      <polyline points={pts.join(" ")} fill="none" stroke={color}
        strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
        vectorEffect="non-scaling-stroke" />
    </svg>
  );
}