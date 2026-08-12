import * as TabsPrimitive from "@radix-ui/react-tabs";
import { forwardRef } from "react";
import { cn } from "../../lib/utils.js";

export const Tabs = TabsPrimitive.Root;

export const TabsList = forwardRef(function TabsList({ className, ...props }, ref) {
  return (
    <TabsPrimitive.List
      ref={ref}
      className={cn(
        "inline-flex items-center overflow-hidden rounded-control border border-line",
        className,
      )}
      {...props}
    />
  );
});

export const TabsTrigger = forwardRef(function TabsTrigger({ className, ...props }, ref) {
  return (
    <TabsPrimitive.Trigger
      ref={ref}
      className={cn(
        "h-8 border-r border-line px-4 text-xs text-ink-2 outline-none transition-colors last:border-r-0 hover:text-ink focus-visible:bg-surface-2 data-[state=active]:bg-ink data-[state=active]:font-semibold data-[state=active]:text-canvas",
        className,
      )}
      {...props}
    />
  );
});

export const TabsContent = forwardRef(function TabsContent({ className, ...props }, ref) {
  return <TabsPrimitive.Content ref={ref} className={cn("mt-4", className)} {...props} />;
});
