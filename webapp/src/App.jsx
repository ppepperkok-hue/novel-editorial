import { useCallback, useEffect, useRef, useState } from "react";
import { getDashboard } from "./api.js";
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
  executions: ["执行记录", "日更与周会工作流的最近执行历史"],
  reader: ["阅读数据", "完读率、追读率趋势与读者反馈报告"],
  settings: ["系统设置", "运行开关、预算、目标字数与风格微调"],
};

export default function App() {
  const pageFromHash = () => {
    const h = (location.hash || "").replace("#", "");
    return NAV.some((n) => n.id === h) ? h : "dashboard";
  };
  const [page, setPage] = useState(pageFromHash);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [toasts, setToasts] = useState([]);
  const toastId = useRef(0);

  const pushToast = useCallback((text, kind = "ok") => {
    const id = ++toastId.current;
    setToasts((t) => [...t, { id, text, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4200);
  }, []);

  const refresh = useCallback(async () => {
    try {
      setData(await getDashboard());
      setError("");
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, [refresh]);

  useEffect(() => {
    const onHash = () => setPage(pageFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const go = (id) => {
    setPage(id);
    if (location.hash !== "#" + id) location.hash = id;
  };

  const wf = data?.health?.workflows;
  const online = wf?.daily?.online;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-logo">笔</div>
          <div>
            <div className="brand-name">小说流水线</div>
            <div className="brand-sub">Novel Pipeline Console</div>
          </div>
        </div>

        <nav>
          {NAV.map((n) => (
            <div
              key={n.id}
              className={`nav-item ${page === n.id ? "active" : ""}`}
              onClick={() => go(n.id)}
            >
              <span className="nav-icon">{n.icon}</span>
              {n.label}
            </div>
          ))}
        </nav>

        <div className="sidebar-foot">
          <div className="mb-2 flex items-center">
            <span className="dot" style={{ background: online ? "#34d399" : "#f87171" }} />
            n8n {online ? "在线" : "离线"}
          </div>
          <div>数据更新 {data?.updated_at || "—"}</div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <div className="topbar-title">{PAGE_META[page][0]}</div>
            <div className="topbar-sub">{PAGE_META[page][1]}</div>
          </div>
          <div className="flex items-center gap-2">
            {error ? (
              <span className="chip chip-bad">连接失败</span>
            ) : (
              <span className="chip chip-ok">● 实时</span>
            )}
            <button className="btn" onClick={refresh}>
              ⟳ 刷新
            </button>
          </div>
        </header>

        <div className="content fade-page">
          {page === "dashboard" && <DashboardPage data={data} error={error} onRefresh={refresh} pushToast={pushToast} />}
          {page === "works" && <WorksPage data={data} />}
          {page === "chapters" && <ChaptersPage data={data} />}
          {page === "agents" && <AgentsPage pushToast={pushToast} />}
          {page === "cost" && <CostPage data={data} />}
          {page === "executions" && <ExecutionsPage />}
          {page === "reader" && <ReaderPage data={data} />}
          {page === "settings" && <SettingsPage data={data} onRefresh={refresh} pushToast={pushToast} />}
        </div>
      </main>

      <div className="toast-wrap">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.kind}`}>{t.text}</div>
        ))}
      </div>
    </div>
  );
}
