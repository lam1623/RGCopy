import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

export const buttonVariants = cva(
  "inline-flex shrink-0 select-none items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-medium outline-none transition-[color,background-color,border-color,box-shadow,transform,filter] duration-150 focus-visible:ring-2 focus-visible:ring-ring active:scale-[0.98] disabled:pointer-events-none disabled:opacity-45 [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary:
          "bg-brand text-accent-fg shadow-[0_8px_24px_-12px_var(--glow)] hover:brightness-110 hover:shadow-[0_10px_28px_-10px_var(--glow)]",
        secondary: "border border-border bg-surface text-fg shadow-card hover:border-border-strong hover:bg-elevated",
        ghost: "text-muted hover:bg-elevated hover:text-fg",
        outline: "border border-border-strong text-fg hover:bg-elevated",
        danger: "border border-danger/25 bg-danger/10 text-danger hover:bg-danger/15",
        subtle: "bg-accent-soft text-accent hover:bg-accent-soft/80",
      },
      size: {
        xs: "h-7 gap-1.5 rounded-md px-2.5 text-xs [&_svg]:size-3.5",
        sm: "h-8 px-3 text-[13px]",
        md: "h-9 px-3.5",
        lg: "h-11 rounded-xl px-5 text-[15px] [&_svg]:size-[18px]",
        icon: "size-8 p-0",
        "icon-sm": "size-7 rounded-md p-0 [&_svg]:size-3.5",
      },
    },
    defaultVariants: { variant: "secondary", size: "md" },
  },
);

export type ButtonProps = ComponentProps<"button"> & VariantProps<typeof buttonVariants> & { asChild?: boolean };

export function Button({ className, variant, size, asChild, type, ...props }: ButtonProps) {
  const Comp = asChild ? Slot.Root : "button";
  return (
    <Comp
      type={asChild ? undefined : (type ?? "button")}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  );
}
