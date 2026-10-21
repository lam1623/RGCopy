import type { ComponentProps, ReactNode } from "react";
import { useT } from "@/lib/i18n";
import type { JobStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

export function Badge({ className, ...props }: ComponentProps<"span">) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md border border-border bg-elevated px-1.5 py-0.5 text-[11px] font-medium leading-none text-muted",
        className,
      )}
      {...props}
    />
  );
}

export function Kbd({ className, ...props }: ComponentProps<"kbd">) {
  return (
    <kbd
      className={cn(
        "inline-flex h-5 min-w-5 items-center justify-center rounded border border-border-strong bg-surface px-1 font-sans text-[11px] font-medium text-muted shadow-card",
        className,
      )}
      {...props}
    />
  );
}

export function Field({
  label,
  hint,
  aside,
  children,
  className,
}: {
  label: ReactNode;
  hint?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex items-center justify-between gap-3">
        <div className="text-[13px] font-medium text-fg">{label}</div>
        {aside && <div className="text-xs text-muted tabular">{aside}</div>}
      </div>
      {children}
      {hint && <p className="text-xs leading-relaxed text-subtle">{hint}</p>}
    </div>
  );
}

export function SectionTitle({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <h3 className={cn("text-[11px] font-semibold uppercase tracking-[0.08em] text-subtle", className)}>{children}</h3>
  );
}

export function Row({
  title,
  description,
  control,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  control: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex items-center justify-between gap-6 py-3.5", className)}>
      <div className="min-w-0">
        <div className="text-sm font-medium text-fg">{title}</div>
        {description && <div className="mt-0.5 text-[13px] leading-relaxed text-muted">{description}</div>}
      </div>
      <div className="shrink-0">{control}</div>
    </div>
  );
}

const STATUS_STYLES: Record<JobStatus, string> = {
  scanning: "bg-info/12 text-info",
  queued: "bg-elevated text-muted",
  running: "bg-accent-soft text-accent",
  paused: "bg-warning/12 text-warning",
  completed: "bg-success/12 text-success",
  failed: "bg-danger/12 text-danger",
  canceled: "bg-elevated text-subtle",
};

export function StatusBadge({
  status,
  moving,
  className,
}: {
  status: JobStatus;
  moving?: boolean;
  className?: string;
}) {
  const t = useT();
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-semibold",
        STATUS_STYLES[status],
        className,
      )}
    >
      <span
        className={cn("size-1.5 rounded-full bg-current", (status === "running" || status === "scanning") && "animate-pulse")}
      />
      {moving && status === "running" ? t("status.moving") : t(`status.${status}`)}
    </span>
  );
}

const BAR_COLORS: Record<JobStatus, string> = {
  scanning: "bg-border-strong",
  queued: "bg-border-strong",
  running: "bg-brand",
  paused: "bg-warning",
  completed: "bg-success",
  failed: "bg-danger",
  canceled: "bg-subtle",
};

export function ProgressBar({
  value,
  status = "running",
  indeterminate,
  className,
}: {
  value: number;
  status?: JobStatus;
  indeterminate?: boolean;
  className?: string;
}) {
  const width = Math.max(0, Math.min(100, value));
  return (
    <div
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={indeterminate ? undefined : Math.round(width)}
      className={cn("relative h-1.5 overflow-hidden rounded-full bg-fg/8", className)}
    >
      {indeterminate ? (
        <div className="absolute inset-y-0 w-2/5 rounded-full bg-brand animate-indeterminate" />
      ) : (
        <div
          className={cn(
            "relative h-full overflow-hidden rounded-full transition-[width] duration-500 ease-out",
            BAR_COLORS[status],
          )}
          style={{ width: `${width}%` }}
        >
          {status === "running" && <div className="absolute inset-0 stripes animate-shimmer opacity-60" />}
        </div>
      )}
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      className={cn("inline-block size-4 animate-spin rounded-full border-2 border-current border-r-transparent", className)}
    />
  );
}
