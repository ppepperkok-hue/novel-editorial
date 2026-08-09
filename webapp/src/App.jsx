import { useCallback, useEffect, useRef, useState } from "react";
import { getControl, getDashboard } from "./api.js";
import { ErrorBoundary } from "./components/ui.jsx";
import DashboardPage from "./components/DashboardPage.jsx";
import WorksPage from "./components/WorksPage.jsx";
import ChaptersPage from "./components/ChaptersPage.jsx";
import AgentsPage from "./components/AgentsPage.jsx";
import CostPage from "./components/CostPage.jsx";
import ExecutionsPage from "./components/ExecutionsPage.jsx";
import ReaderPage from "./components/ReaderPage.jsx";
import SettingsPage from "./components/SettingsPage.jsx";

const NAV = [
  { id: "dashboard", label: "仪表盘", icon: "◈" },
  { id: "works", label: "作品库", icon: "▤" },
  { id: "chapters", label: "章节管理", icon: "≡" },
  { id: "agents", label: "Agent 管理", icon: "◇" },
  { id: "cost", label: "成本中心", icon: "¥" },
  { id: "executions", label: "执行记录", icon: "⏱" },
  { id: "reader", label: "阅读数据", icon: "◔" },
  { id: "settings", label: "系统设置", icon: "⚙" },
];

const PAGE_META = {
  dashboard: ["仪表盘", "流水线实时总览：作品、质量、成本、健康与热点"],
  works: ["作品库", "每部作品的完整设定：大纲、主角、角色卡与世界规则"],
  chapters: ["章节管理", "全部章节的写作状态、评分与发布进度"],
  agents: ["Agent 管理", "编辑每个写作智能体的提示词、模型与温度，保存后一键部署"],
  cost: ["成本中心", "API 花费按日与按节点统计，控制月预算"],
  executions: ["执行记录", "日更与周会工作流的最近执行历史与失败详情"],
  reader: ["阅读数据", "完读率、追读率趋势与读者反馈报告"],
  settings: ["系统设置", "运行开关、预算、目标字数、更新时间与风格微调"],
};

const TOAST_ICON = { ok: "✓", bad: "✕", warn: "!" };
const desktopApi = typeof window !== "undefined" ? window.desktopApi || null : null;

function TitleBar() {
  const [maximized, setMaximized] = useState(false);
  useEffect(() => {
    desktopApi?.isMaximized?.().then(setMaximized).catch(() => {});
  }, []);
  return (
    <header className="titlebar">
      <div className="titlebar-brand">
        <span className="titlebar-logo">笔</span>
        <span className="titlebar-name">小说流水线</span>
        <span className="titlebar-sub">Novel Pipeline Console</span>
      </div>
      <div className="titlebar-controls">
        <button className="win-btn" title="最小化" onClick={() => desktopApi.minimize()}>─</button>
        <button
          className="win-btn"
          title={maximized ? "还原" : "最大化"}
          onClick={async () => {
            await desktopApi.maximize();
            setMaximized(await desktopApi.isMaximized());
          }}
        >
          {maximized ? "❐" : "▢"}
        </button>
        <button className="win-btn win-close" title="关闭" onClick={() => desktopApi.close()}>✕</button>
      </div>
    </header>
  );
}

function SidebarSkeleton() {
  return (
    <aside className="sidebar">
      <div className="skeleton mb-4 h-9 w-44" />
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="skeleton mb-2 h-8 w-full" />
      ))}
    </aside>
  );
}

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
  const toastId = useRef(0);

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
    const onHash = () => setPage(pageFromHash());
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "r") {
        e.preventDefault();
        refresh();
      }
    };
    window.addEventListener("hashchange", onHash);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("hashchange", onHash);
      window.removeEventListener("keydown", onKey);
    };
  }, [refresh]);

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

  const wf = control?.workflows || {};
  const online = wf.daily?.online || wf.weekly?.online;

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
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-logo">笔</div>
          {!mini && (
            <div>
              <div className="brand-name">小说流水线</div>
              <div className="brand-sub">Novel Pipeline</div>
            </div>
          )}
        </div>

        <nav>
          {NAV.map((n) => (
            <div
              key={n.id}
              className={`nav-item ${page === n.id ? "active" : ""}`}
              title={mini ? n.label : undefined}
              onClick={() => go(n.id)}
            >
              <span className="nav-icon">{n.icon}</span>
              {!mini && n.label}
            </div>
          ))}
        </nav>

        <div className="sidebar-foot">
          <div className={`mb-2 flex items-center ${mini ? "justify-center" : ""}`}>
            <span className={`dot ${online ? "ok" : "bad"}`} />
            {!mini && <>n8n {online ? "在线" : "离线"}</>}
          </div>
          {!mini && (
            <>
              <div>数据更新 {data?.updated_at || "—"}</div>
              <button className="sidebar-mini-btn" onClick={toggleMini}>⇤ 收起侧栏</button>
            </>
          )}
          {mini && (
            <button className="sidebar-mini-btn" onClick={toggleMini} title="展开侧栏">⇥</button>
          )}
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <div className="topbar-title">{PAGE_META[page][0]}</div>
            <div className="topbar-sub">{PAGE_META[page][1]}</div>
          </div>
          <div className="flex items-center gap-2">
            <span className="muted hidden text-xs tabular-nums sm:inline">
              {now.toLocaleDateString("zh-CN")} {now.toLocaleTimeString("zh-CN", { hour12: false })}
            </span>
            {error ? (
              <span className="chip chip-bad" title={error}>连接失败</span>
            ) : (
              <span className="chip chip-ok">● 实时</span>
            )}
            <button className="btn" onClick={refresh} disabled={refreshing}>
              <span className={refreshing ? "spin" : ""}>⟳</span> 刷新
            </button>
          </div>
        </header>

        <div className="content fade-page">
          <ErrorBoundary>
            {page === "dashboard" && <DashboardPage data={data} error={error} onRefresh={refresh} pushToast={pushToast} />}
            {page === "works" && <WorksPage data={data} />}
            {page === "chapters" && <ChaptersPage data={data} />}
            {page === "agents" && <AgentsPage pushToast={pushToast} />}
            {page === "cost" && <CostPage data={data} />}
            {page === "executions" && <ExecutionsPage />}
            {page === "reader" && <ReaderPage data={data} />}
            {page === "settings" && <SettingsPage data={data} onRefresh={refresh} pushToast={pushToast} />}
          </ErrorBoundary>
        </div>
      </main>
      </div>

      <div className="toast-wrap">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.kind}`}>
            <span className="toast-icon">{TOAST_ICON[t.kind]}</span>
            {t.text}
          </div>
        ))}
      </div>
    </div>
  );
}
