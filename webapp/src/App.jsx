import { useCallback, useEffect, useRef, useState } from "react";
import { getControl, getDashboard, subscribeEvents } from "./api.js";
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
  const [data, setData] = useState(null);
  const [control, setControl] = useState(null);
  const [error, setError] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [mini, setMini] = useState(() => localStorage.getItem("panel_mini") === "1");
  const [toasts, setToasts] = useState([]);
  const [now, setNow] = useState(new Date());
  const [liveSnapshot, setLiveSnapshot] = useState(null);
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

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      setData(await getDashboard());
      setError("");
    } catch (e) {
      setError(String(e));
    } finally {
      setRefreshing(false);
    }
  }, []);

  const refreshControl = useCallback(async () => {
    try {
      setControl(await getControl());
    } catch {
      setControl(null);
    }
  }, []);

  useEffect(() => {
    refresh();
    refreshControl();
    const t = setInterval(refresh, 5000);
    const tc = setInterval(refreshControl, 15000);
    const tk = setInterval(() => setNow(new Date()), 1000);
    return () => {
      clearInterval(t);
      clearInterval(tc);
      clearInterval(tk);
    };
  }, [refresh, refreshControl]);

  useEffect(() => {
    const es = subscribeEvents((snap) => {
      setLiveSnapshot(snap);
    });
    return () => es.close();
  }, []);

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
          </main>
        </div>
      </div>
    );
  }

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
            {page === "dashboard" && <DashboardPage data={data} error={error} onRefresh={refresh} pushToast={pushToast} snapshot={liveSnapshot} />}
            {page === "works" && <WorksPage data={data} pushToast={pushToast} />}
            {page === "chapters" && <ChaptersPage data={data} />}
            {page === "agents" && <AgentsPage pushToast={pushToast} />}
            {page === "cost" && <CostPage data={data} />}
            {page === "executions" && <ExecutionsPage snapshot={liveSnapshot} />}
            {page === "flow" && <FlowPage />}
            {page === "editorial" && <EditorialPage />}
            {page === "reader" && <ReaderPage data={data} />}
            {page === "settings" && <SettingsPage data={data} onRefresh={refresh} pushToast={pushToast} theme={theme} onThemeChange={changeTheme} />}
            {page === "meetings" && <MeetingsPage />}
            {page === "audit" && <AuditPage />}
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
