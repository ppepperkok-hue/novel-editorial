import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** 合并 Tailwind 类名（shadcn 惯例，@stable）。 */
export function cn(...inputs) {
  return twMerge(clsx(inputs));
}
