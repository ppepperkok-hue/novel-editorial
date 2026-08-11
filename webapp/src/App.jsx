import { useCallback, useEffect, useRef, useState } from "react";
import { subscribeEvents } from "./api.js";
import { usePolling } from "./hooks.js";
import { usePipelineStore } from "./stores.js";
import { ErrorBoundary } from "./components/ui.jsx";
import DashboardPage from "./components/DashboardPage.jsx";
import WorksPage from "./components/WorksPage.jsx";
import ChaptersPage from "./components/ChaptersPage.jsx";
import AgentsPage from "./components/AgentsPage.jsx";
import CostPage from "./components/CostPage.jsx";
import ExecutionsPage from "./components/ExecutionsPage.jsx";
import FlowPage from "./components/FlowPage.jsx";
import EditorialPage from "./components/EditorialPage.jsx";
import ReaderPage from "./components/ReaderPage.jsx";
import SettingsPage from "./components/SettingsPage.jsx";
import CommandPalette from "./components/CommandPalette.jsx";
import MeetingsPage from "./components/MeetingsPage.jsx";
import AuditPage from "./components/AuditPage.jsx";
import {
  HelpModal,
  NAV,
  Sidebar,
  SidebarSkeleton,
  TitleBar,
  Toasts,
  Topbar,
  desktopApi,
} from "./components/Shell.jsx";

export default function App() {
  const pageFromHash = () => {
    const h = (location.hash || "").replace("#", "");
    return NAV.some((n) => n.id === h) ? h : "dashboard";
  };
  const [page, setPage] = useState(pageFromHash);
  const data = usePipelineStore((s) => s.data);
  const control = usePipelineStore((s) => s.control);
  const liveSnapshot = usePipelineStore((s) => s.liveSnapshot);
  const fetchDashboard = usePipelineStore((s) => s.fetchDashboard);
  const fetchControl = usePipelineStore((s) => s.fetchControl);
  const setLiveSnapshot = usePipelineStore((s) => s.setLiveSnapshot);
  const [refreshing, setRefreshing] = useState(false);
  const [mini, setMini] = useState(() => localStorage.getItem("panel_mini") === "1");
  const [toasts, setToasts] = useState([]);
  const [now, setNow] = useState(new Date());
  const [helpOpen, setHelpOpen] = useState(false);
  const toastId = useRef(0);
  const [theme, setTheme] = useState(() => {
    const urlTheme = new URLSearchParams(location.search).get("theme");
    return urlTheme || localStorage.getItem("panel_theme") || "dark";
  });

  const pushToast = useCallback((text, kind = "ok") => {
    const id = ++toastId.current;
    setToasts((t) => [...t, { id, text, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4600);
  }, []);

  const [dashboardError] = usePolling(fetchDashboard, 5000);
  usePolling(fetchControl, 15000);
  const error = dashboardError;
  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await fetchDashboard();
    } catch (e) {
      console.error("refresh failed", e);
    } finally {
      setRefreshing(false);
    }
  }, [fetchDashboard]);

  useEffect(() => {
    const tk = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(tk);
  }, []);

  useEffect(() => {
    const es = subscribeEvents((snap) => {
      setLiveSnapshot(snap);
    });
    return () => es.close();
  }, [setLiveSnapshot]);

  useEffect(() => {
    const onHash = () => setPage(pageFromHash());
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "r") {
        e.preventDefault();
        refresh();
        return;
      }
      if (e.key === "?") {
        setHelpOpen((v) => !v);
        return;
      }
      const tag = (e.target?.tagName || "").toLowerCase();
      if (["input", "textarea", "select"].includes(tag) || e.ctrlKey || e.metaKey || e.altKey) {
        return;
      }
      const num = Number(e.key);
      if (num >= 1 && num <= NAV.length) {
        go(NAV[num - 1].id);
      }
    };
    window.addEventListener("hashchange", onHash);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("hashchange", onHash);
      window.removeEventListener("keydown", onKey);
    };
  }, [refresh]);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      const resolved = theme === "system" ? (mq.matches ? "dark" : "light") : theme;
      document.documentElement.setAttribute("data-theme", resolved);
    };
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [theme]);

  const changeTheme = (t) => {
    localStorage.setItem("panel_theme", t);
    setTheme(t);
  };

  const go = (id) => {
    setPage(id);
    if (location.hash !== "#" + id) location.hash = id;
  };

  const toggleMini = () => {
    setMini((m) => {
      localStorage.setItem("panel_mini", m ? "0" : "1");
      return !m;
    });
  };

  const online = Boolean(control?.scheduler);

  if (!data) {
    return (
      <div className="app-shell">
        {desktopApi ? <TitleBar /> : null}
        <div className="app-body">
          <SidebarSkeleton />
          <main className="main">
            {error ? (
              <div className="content">
                <div className="panel p-6 text-center">
                  <div className="text-base font-bold">无法连接后端服务</div>
                  <div className="muted mt-2 text-sm">{error}</div>
                  <button className="btn btn-primary mt-4" disabled={refreshing} onClick={refresh}>
                    {refreshing ? "重试中…" : "重试"}
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div className="topbar">
                  <div className="skeleton h-6 w-40" />
                  <div className="skeleton h-8 w-28" />
                </div>
                <div className="content">
                  <div className="kpi-grid">
                    {Array.from({ length: 9 }).map((_, i) => (
                      <div key={i} className="card kpi">
                        <div className="skeleton mb-2 h-3 w-16" />
                        <div className="skeleton h-7 w-20" />
                      </div>
                    ))}
                  </div>
                  <div className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-3">
                    {Array.from({ length: 3 }).map((_, i) => (
                      <div key={i} className="panel p-4">
                        <div className="skeleton mb-3 h-4 w-32" />
                        <div className="skeleton h-24 w-full" />
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}
          </main>
        </div>
      </div>
    );
  }

  const routes = {
    dashboard: () => (
      <DashboardPage data={data} error={error} onRefresh={refresh} pushToast={pushToast} snapshot={liveSnapshot} />
    ),
    works: () => <WorksPage data={data} pushToast={pushToast} />,
    chapters: () => <ChaptersPage data={data} />,
    agents: () => <AgentsPage pushToast={pushToast} />,
    cost: () => <CostPage data={data} />,
    executions: () => <ExecutionsPage snapshot={liveSnapshot} />,
    flow: () => <FlowPage />,
    editorial: () => <EditorialPage />,
    reader: () => <ReaderPage data={data} />,
    settings: () => (
      <SettingsPage data={data} onRefresh={refresh} pushToast={pushToast} theme={theme} onThemeChange={changeTheme} />
    ),
    meetings: () => <MeetingsPage />,
    audit: () => <AuditPage />,
  };

  return (
    <div className={`app-shell ${mini ? "mini-sidebar" : ""}`}>
      {desktopApi ? <TitleBar /> : null}
      <div className="app-body">
      <Sidebar
        page={page}
        go={go}
        mini={mini}
        toggleMini={toggleMini}
        online={online}
        liveSnapshot={liveSnapshot}
        data={data}
      />

      <main className="main">
        <Topbar page={page} now={now} error={error} refreshing={refreshing} refresh={refresh} />

        <div className="content fade-page">
          <ErrorBoundary>
            {routes[page] ? routes[page]() : null}
          </ErrorBoundary>
        </div>
      </main>
      </div>

      <Toasts toasts={toasts} />

      <CommandPalette
        onRefresh={refresh}
        pushToast={pushToast}
        go={go}
        changeTheme={changeTheme}
        theme={theme}
      />

      <HelpModal open={helpOpen} onClose={() => setHelpOpen(false)} />
    </div>
  );
}
