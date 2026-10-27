import { useId } from "react";
import { SPEED_SAMPLES } from "@/lib/store";
import { cn } from "@/lib/utils";
import type { Tone } from "./ui/bars";

// Never stretch fewer samples than this over the whole width (a lone sample is not a trend)
const MIN_SPAN = 36;

const STROKES: Record<Tone, string> = {
  active: "var(--accent)",
  paused: "var(--warning)",
  done: "var(--success)",
  failed: "var(--danger)",
  waiting: "var(--subtle)",
};

/** Area chart of the transfer speed, newest sample on the right (like a copy dialog). */
export function SpeedChart({ samples, tone, className }: { samples: number[]; tone: Tone; className?: string }) {
  const id = useId();
  const width = 300;
  const height = 92;
  const peak = Math.max(1, ...samples) * 1.25;
  // Few samples stretch across the chart; once it is full it scrolls (newest on the right)
  const step = width / Math.max(MIN_SPAN, Math.min(SPEED_SAMPLES, samples.length) - 1);
  const points = samples.map((value, index) => {
    const x = width - (samples.length - 1 - index) * step;
    // The top 28 px stay free for the labels drawn over the chart
    const y = height - (value / peak) * (height - 28);
    return [x, y] as const;
  });
  const line = points.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  const area = points.length > 1 ? `${line} L${width} ${height} L${points[0][0].toFixed(1)} ${height} Z` : "";
  const stroke = STROKES[tone];

  return (
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden className={cn("h-full w-full", className)}>
      <defs>
        <linearGradient id={`${id}-fill`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={stroke} stopOpacity="0.38" />
          <stop offset="1" stopColor={stroke} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      {[0.25, 0.5, 0.75].map((f) => (
        <line key={f} x1="0" x2={width} y1={height * f} y2={height * f} stroke="var(--border)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
      ))}
      {points.length > 1 && (
        <>
          <path d={area} fill={`url(#${id}-fill)`} />
          <path d={line} fill="none" stroke={stroke} strokeWidth="2.2" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
        </>
      )}
    </svg>
  );
}
