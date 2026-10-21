import { cn } from "@/lib/utils";

/** Two stacked pages with an arrow: a copy on its way. */
export function Logo({ className, size = "md" }: { className?: string; size?: "sm" | "md" | "lg" }) {
  const box = size === "lg" ? "size-14 rounded-2xl" : size === "sm" ? "size-7 rounded-lg" : "size-9 rounded-xl";
  const icon = size === "lg" ? "size-9" : size === "sm" ? "size-[18px]" : "size-6";
  return (
    <div
      className={cn(
        "grid shrink-0 place-items-center bg-brand text-white shadow-[0_8px_24px_-10px_var(--glow)] ring-1 ring-white/15 ring-inset",
        box,
        className,
      )}
    >
      <svg viewBox="0 0 24 24" className={icon} fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <rect x="3.5" y="3" width="10" height="12.5" rx="2" opacity={0.55} />
        <rect x="9.5" y="8.5" width="11" height="12.5" rx="2" className="fill-[var(--brand-from)]" />
        <path d="M12.5 15h5M15.5 12.5 18 15l-2.5 2.5" />
      </svg>
    </div>
  );
}
