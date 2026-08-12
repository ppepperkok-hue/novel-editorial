import { useEffect, useState } from "react";
import { HashRouter } from "react-router-dom";
import { Toaster, toast } from "sonner";
import { AppShell } from "../components/layout/app-shell.jsx";
import { usePipelineStore } from "../stores.js";

function resolveTheme(pref) {
  if (pref === "system") {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return pref;
}

/** 应用根：主题、数据轮询、路由壳。@stable */
export default function App() {
  const [theme, setTheme] = useState(() => {
    const urlTheme = new URLSearchParams(location.search).get("theme");
    return urlTheme || localStorage.getItem("panel_theme") || "dark";
  });
  const [refreshing, setRefreshing] = useState(false);
  const fetchDashboard = usePipelineStore((s) => s.fetchDashboard);
  const fetchControl = usePipelineStore((s) => s.fetchControl);
  const control = usePipelineStore((s) => s.control);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      document.documentElement.setAttribute("data-theme", resolveTheme(theme));
    };
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [theme]);

  useEffect(() => {
    const poll = () => {
      fetchDashboard().catch(() => {});
      fetchControl().catch(() => {});
    };
    poll();
    const dashboardTimer = setInterval(() => fetchDashboard().catch(() => {}), 10000);
    const controlTimer = setInterval(() => fetchControl().catch(() => {}), 30000);
    return () => {
      clearInterval(dashboardTimer);
      clearInterval(controlTimer);
    };
  }, [fetchDashboard, fetchControl]);

  const refresh = async () => {
    if (refreshing) return;
    setRefreshing(true);
    try {
      await Promise.all([fetchDashboard(), fetchControl()]);
      toast.success("数据已刷新");
    } catch {
      toast.error("刷新失败");
    } finally {
      setRefreshing(false);
    }
  };

  const toggleTheme = () => {
    const next = resolveTheme(theme) === "dark" ? "light" : "dark";
    setTheme(next);
    localStorage.setItem("panel_theme", next);
  };

  return (
    <HashRouter>
      <AppShell
        theme={theme}
        onToggleTheme={toggleTheme}
        onRefresh={refresh}
        schedulerOnline={Boolean(control?.scheduler)}
      />
      <Toaster theme={resolveTheme(theme)} position="bottom-right" />
    </HashRouter>
  );
}
