import { cva } from "class-variance-authority";
import { forwardRef } from "react";
import { cn } from "../../lib/utils.js";

export const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-control text-sm font-medium transition-colors active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "border border-ink bg-ink text-canvas hover:opacity-85",
        outline:
          "border border-line bg-surface text-ink-2 hover:border-line-strong hover:bg-surface-2 hover:text-ink",
        ghost: "text-ink-2 hover:bg-surface-2 hover:text-ink",
        accent: "bg-accent text-white hover:opacity-85 border border-transparent",
        danger: "border border-bad/40 bg-bad-soft text-bad hover:bg-bad-soft",
        ok: "border border-ok/40 bg-ok-soft text-ok hover:bg-ok-soft",
      },
      size: {
        sm: "h-8 px-3 text-xs",
        default: "h-9 px-4 text-sm",
        lg: "h-11 px-6 text-sm",
        icon: "size-8",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export const Button = forwardRef(function Button(
  { className, variant, size, type = "button", ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  );
});
