import { MagnifyingGlass } from "@phosphor-icons/react";
import { Command as CommandPrimitive } from "cmdk";
import { forwardRef } from "react";
import { cn } from "../../lib/utils.js";

export const Command = forwardRef(function Command({ className, ...props }, ref) {
  return (
    <CommandPrimitive
      ref={ref}
      className={cn("flex size-full flex-col overflow-hidden text-ink", className)}
      {...props}
    />
  );
});

export function CommandInput({ className, ...props }) {
  return (
    <div className="flex items-center gap-2 border-b border-line px-3">
      <MagnifyingGlass className="size-4 shrink-0 text-ink-3" />
      <CommandPrimitive.Input
        className={cn(
          "h-11 w-full bg-transparent text-sm text-ink outline-none placeholder:text-ink-3",
          className,
        )}
        {...props}
      />
    </div>
  );
}

export const CommandList = CommandPrimitive.List;
export const CommandEmpty = CommandPrimitive.Empty;
export const CommandGroup = CommandPrimitive.Group;
export const CommandItem = CommandPrimitive.Item;

export function CommandSeparator({ className, ...props }) {
  return (
    <CommandPrimitive.Separator className={cn("-mx-1 h-px bg-line", className)} {...props} />
  );
}
