import { Check, ChevronDown } from "lucide-react";
import { Checkbox as RCheckbox, Select as RSelect, Slider as RSlider, Switch as RSwitch, ToggleGroup } from "radix-ui";
import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface Option<T extends string = string> {
  value: T;
  label: ReactNode;
  hint?: ReactNode;
  disabled?: boolean;
}

export function Select<T extends string>({
  value,
  onValueChange,
  options,
  disabled,
  className,
  placeholder,
  "aria-label": ariaLabel,
}: {
  value: T;
  onValueChange: (value: T) => void;
  options: Option<T>[];
  disabled?: boolean;
  className?: string;
  placeholder?: string;
  "aria-label"?: string;
}) {
  return (
    <RSelect.Root value={value} onValueChange={(v) => onValueChange(v as T)} disabled={disabled}>
      <RSelect.Trigger
        aria-label={ariaLabel}
        className={cn(
          "flex h-9 w-full items-center justify-between gap-2 rounded-lg border border-border bg-surface px-3 text-left text-sm text-fg shadow-card outline-none transition hover:border-border-strong focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50 data-[placeholder]:text-subtle",
          className,
        )}
      >
        <span className="truncate">
          <RSelect.Value placeholder={placeholder} />
        </span>
        <RSelect.Icon>
          <ChevronDown className="size-4 text-subtle" />
        </RSelect.Icon>
      </RSelect.Trigger>
      <RSelect.Portal>
        <RSelect.Content
          position="popper"
          sideOffset={6}
          className="z-50 max-h-[min(360px,var(--radix-select-content-available-height))] min-w-[var(--radix-select-trigger-width)] overflow-hidden rounded-xl border border-border-strong bg-panel p-1 shadow-2xl animate-fade-in"
        >
          <RSelect.Viewport>
            {options.map((option) => (
              <RSelect.Item
                key={option.value}
                value={option.value}
                disabled={option.disabled}
                className="relative flex cursor-pointer select-none items-center gap-2 rounded-lg py-2 pl-8 pr-3 text-sm text-fg outline-none data-[disabled]:cursor-default data-[highlighted]:bg-elevated data-[disabled]:opacity-40"
              >
                <RSelect.ItemIndicator className="absolute left-2.5">
                  <Check className="size-3.5 text-accent" />
                </RSelect.ItemIndicator>
                <div className="min-w-0">
                  <RSelect.ItemText>{option.label}</RSelect.ItemText>
                  {option.hint && <div className="text-xs text-subtle">{option.hint}</div>}
                </div>
              </RSelect.Item>
            ))}
          </RSelect.Viewport>
        </RSelect.Content>
      </RSelect.Portal>
    </RSelect.Root>
  );
}

export function Slider({
  value,
  min,
  max,
  step = 1,
  onValueChange,
  onValueCommit,
  disabled,
  className,
  "aria-label": ariaLabel,
}: {
  value: number;
  min: number;
  max: number;
  step?: number;
  onValueChange?: (value: number) => void;
  onValueCommit?: (value: number) => void;
  disabled?: boolean;
  className?: string;
  "aria-label"?: string;
}) {
  return (
    <RSlider.Root
      value={[value]}
      min={min}
      max={max}
      step={step}
      disabled={disabled}
      onValueChange={([v]) => onValueChange?.(v)}
      onValueCommit={([v]) => onValueCommit?.(v)}
      className={cn("relative flex h-5 w-full touch-none select-none items-center data-[disabled]:opacity-45", className)}
    >
      <RSlider.Track className="relative h-1.5 grow overflow-hidden rounded-full bg-elevated">
        <RSlider.Range className="absolute h-full rounded-full bg-brand" />
      </RSlider.Track>
      <RSlider.Thumb
        aria-label={ariaLabel}
        className="block size-4 rounded-full border-2 border-accent bg-white shadow-md outline-none transition-transform hover:scale-110 focus-visible:ring-4 focus-visible:ring-ring"
      />
    </RSlider.Root>
  );
}

export function Switch({ className, ...props }: ComponentProps<typeof RSwitch.Root>) {
  return (
    <RSwitch.Root
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border border-border-strong bg-elevated transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-45 data-[state=checked]:border-transparent data-[state=checked]:bg-accent",
        className,
      )}
      {...props}
    >
      <RSwitch.Thumb className="pointer-events-none block size-3.5 translate-x-0.5 rounded-full bg-white shadow transition-transform data-[state=checked]:translate-x-[18px]" />
    </RSwitch.Root>
  );
}

export function Segmented<T extends string>({
  value,
  onValueChange,
  options,
  disabled,
  className,
  size = "md",
  "aria-label": ariaLabel,
}: {
  value: T;
  onValueChange: (value: T) => void;
  options: Option<T>[];
  disabled?: boolean;
  className?: string;
  size?: "sm" | "md";
  "aria-label"?: string;
}) {
  return (
    <ToggleGroup.Root
      type="single"
      value={value}
      disabled={disabled}
      aria-label={ariaLabel}
      onValueChange={(v) => v && onValueChange(v as T)}
      className={cn("inline-flex rounded-lg border border-border bg-elevated p-0.5", className)}
    >
      {options.map((option) => (
        <ToggleGroup.Item
          key={option.value}
          value={option.value}
          disabled={option.disabled}
          title={typeof option.hint === "string" ? option.hint : undefined}
          className={cn(
            "inline-flex flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded-md font-medium text-muted outline-none transition hover:text-fg focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-40 data-[state=on]:bg-raised data-[state=on]:text-fg data-[state=on]:shadow-card [&_svg]:size-3.5",
            size === "sm" ? "h-6 px-2 text-xs" : "h-7 px-3 text-[13px]",
          )}
        >
          {option.label}
        </ToggleGroup.Item>
      ))}
    </ToggleGroup.Root>
  );
}

export function Checkbox({ className, ...props }: ComponentProps<typeof RCheckbox.Root>) {
  return (
    <RCheckbox.Root
      className={cn(
        "grid size-4 shrink-0 place-items-center rounded-[5px] border border-border-strong bg-surface outline-none transition focus-visible:ring-2 focus-visible:ring-ring data-[state=checked]:border-accent data-[state=checked]:bg-accent data-[state=indeterminate]:border-accent data-[state=indeterminate]:bg-accent",
        className,
      )}
      {...props}
    >
      <RCheckbox.Indicator>
        {props.checked === "indeterminate" ? (
          <span className="block h-0.5 w-2 rounded bg-white" />
        ) : (
          <Check className="size-3 text-white" strokeWidth={3} />
        )}
      </RCheckbox.Indicator>
    </RCheckbox.Root>
  );
}

export function Input({ className, ...props }: ComponentProps<"input">) {
  return (
    <input
      className={cn(
        "h-9 w-full rounded-lg border border-border bg-surface px-3 text-sm text-fg shadow-card outline-none transition placeholder:text-subtle hover:border-border-strong focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}
