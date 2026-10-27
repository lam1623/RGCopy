import type { JobStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

/** How a bar looks: moving brand stripes while copying, amber paused, green done, red failed. */
export type Tone = "active" | "paused" | "done" | "failed" | "waiting";

export function toneOf(status: JobStatus): Tone {
  switch (status) {
    case "running":
      return "active";
    case "paused":
    case "conflict":
      return "paused";
    case "completed":
      return "done";
    case "failed":
    case "canceled":
      return "failed";
    default:
      return "waiting";
  }
}

const FILLS: Record<Tone, string> = {
  active: "bg-brand shadow-[0_0_14px_-3px_var(--accent)]",
  paused: "bg-gradient-to-r from-amber-500 to-amber-400",
  done: "bg-gradient-to-r from-emerald-600 to-emerald-400",
  failed: "bg-gradient-to-r from-red-600 to-red-400",
  waiting: "bg-border-strong",
};

/** The same gradients for text, e.g. the big percentage. */
export const TONE_TEXT: Record<Tone, string> = {
  active: "bg-brand bg-clip-text text-transparent",
  paused: "bg-gradient-to-r from-amber-600 to-amber-400 bg-clip-text text-transparent",
  done: "bg-gradient-to-r from-emerald-600 to-emerald-400 bg-clip-text text-transparent",
  failed: "bg-gradient-to-r from-red-600 to-red-400 bg-clip-text text-transparent",
  waiting: "text-muted",
};

export const TONE_DOT: Record<Tone, string> = {
  active: "bg-accent",
  paused: "bg-amber-500",
  done: "bg-emerald-500",
  failed: "bg-red-500",
  waiting: "bg-border-strong",
};

function Fill({ value, tone, className }: { value: number; tone: Tone; className?: string }) {
  const width = Math.max(0, Math.min(100, value));
  return (
    <div
      className={cn("relative h-full overflow-hidden rounded-[inherit] transition-[width] duration-300 ease-linear", FILLS[tone], className)}
      style={{ width: `${width}%` }}
    >
      {tone === "active" && <div className="absolute inset-0 stripes animate-shimmer opacity-70" />}
    </div>
  );
}

export function Bar({
  value,
  tone,
  indeterminate,
  className,
  label,
}: {
  value: number;
  tone: Tone;
  indeterminate?: boolean;
  className?: string;
  label?: string;
}) {
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={indeterminate ? undefined : Math.round(value)}
      className={cn("relative h-2.5 overflow-hidden rounded-full bg-fg/8", className)}
    >
      {indeterminate ? (
        <div className="absolute inset-y-0 w-2/5 rounded-full bg-brand animate-indeterminate" />
      ) : (
        <Fill value={value} tone={tone} />
      )}
    </div>
  );
}

export interface Segment {
  id: string;
  /** Relative width (the size of the transfer) */
  weight: number;
  value: number;
  tone: Tone;
  title: string;
  onClick?: () => void;
}

/** One stretch per transfer of the list, as wide as its share of the bytes. */
export function SegmentedBar({ segments, className }: { segments: Segment[]; className?: string }) {
  return (
    <div className={cn("flex h-4 gap-[3px]", className)}>
      {segments.map((segment) => (
        <button
          key={segment.id}
          type="button"
          title={segment.title}
          aria-label={segment.title}
          onClick={segment.onClick}
          style={{ flex: `${Math.max(1, segment.weight)} 1 0px` }}
          className={cn(
            "min-w-2.5 overflow-hidden rounded-[5px] outline-none transition focus-visible:ring-2 focus-visible:ring-ring",
            segment.tone === "waiting"
              ? "bg-[repeating-linear-gradient(135deg,var(--elevated)_0_6px,var(--border-strong)_6px_12px)]"
              : "bg-fg/8",
          )}
        >
          {segment.tone !== "waiting" && <Fill value={segment.value} tone={segment.tone} />}
        </button>
      ))}
    </div>
  );
}
