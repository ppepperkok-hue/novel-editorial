import { useEffect, useState } from "react";
import { MoonStars, Sun } from "@phosphor-icons/react";
import { useNavigate } from "react-router-dom";
import { ALL_PAGES } from "../../lib/nav.js";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "../ui/command.jsx";
import { Dialog, DialogContent, DialogTitle } from "../ui/dialog.jsx";

/** Ctrl+K 命令面板：页面切换 + 主题切换。@stable */
export function CommandPalette({ theme, onToggleTheme, onRefresh }) {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const run = (fn) => () => {
    setOpen(false);
    fn();
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-w-md p-0">
        <DialogTitle className="sr-only">命令面板</DialogTitle>
        <Command>
          <CommandInput placeholder="输入命令或搜索页面…" />
          <CommandList>
            <CommandEmpty>没有匹配的命令</CommandEmpty>
            <CommandGroup heading="页面">
              {ALL_PAGES.map((page) => (
                <CommandItem key={page.id} value={page.id} onSelect={run(() => navigate(`/${page.id}`))}>
                  <page.icon className="size-4 text-ink-2" />
                  {page.label}
                </CommandItem>
              ))}
            </CommandGroup>
            <CommandSeparator />
            <CommandGroup heading="操作">
              <CommandItem value="theme" onSelect={run(onToggleTheme)}>
                {theme === "dark" ? <Sun className="size-4" /> : <MoonStars className="size-4" />}
                切换主题
              </CommandItem>
              <CommandItem value="refresh" onSelect={run(onRefresh)}>
                <span className="size-4 text-center text-sm">↻</span>
                刷新数据
              </CommandItem>
            </CommandGroup>
          </CommandList>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
