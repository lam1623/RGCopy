import { useId } from "react";
import { SPEED_SAMPLES } from "@/lib/store";
import { cn } from "@/lib/utils";

// Never stretch fewer samples than this over the whole width (a lone sample is not a trend)
const MIN_SPAN = 24;

/** Area chart of the transfer speed, newest sample on the right (like a copy dialog). */
export function SpeedChart({ samples, paused, className }: { samples: number[]; paused?: boolean; className?: string }) {
  const id = useId();
  const width = 300;
  const height = 64;
  const peak = Math.max(1, ...samples) * 1.15;
  // Few samples stretch across the chart; once it is full it scrolls (newest on the right)
  const step = width / Math.max(MIN_SPAN, Math.min(SPEED_SAMPLES, samples.length) - 1);
  const points = samples.map((value, index) => {
    const x = width - (samples.length - 1 - index) * step;
    const y = height - (value / peak) * (height - 4);
    return [x, y] as const;
  });
  const line = points.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area = points.length ? `M${points[0][0]},${height} L${line.replace(/ /g, " L")} L${width},${height} Z` : "";

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      aria-hidden
      className={cn("h-16 w-full overflow-visible rounded-lg", className)}
    >
      <defs>
        <linearGradient id={`${id}-fill`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={paused ? "var(--warning)" : "var(--accent)"} stopOpacity="0.35" />
          <stop offset="1" stopColor={paused ? "var(--warning)" : "var(--accent)"} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      {[0.25, 0.5, 0.75].map((f) => (
        <line key={f} x1="0" x2={width} y1={height * f} y2={height * f} stroke="var(--border)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
      ))}
      {points.length > 1 && (
        <>
          <path d={area} fill={`url(#${id}-fill)`} />
          <polyline
            points={line}
            fill="none"
            stroke={paused ? "var(--warning)" : "var(--accent)"}
            strokeWidth="2"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
        </>
      )}
    </svg>
  );
}
