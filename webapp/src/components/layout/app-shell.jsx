import { AnimatePresence, motion } from "motion/react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import DashboardPage from "../../pages/DashboardPage.jsx";
import EditorialPage from "../../pages/EditorialPage.jsx";
import AgentsPage from "../../pages/AgentsPage.jsx";
import MeetingsPage from "../../pages/MeetingsPage.jsx";
import WorksPage from "../../pages/WorksPage.jsx";
import ChaptersPage from "../../pages/ChaptersPage.jsx";
import ReaderPage from "../../pages/ReaderPage.jsx";
import CostPage from "../../pages/CostPage.jsx";
import ExecutionsPage from "../../pages/ExecutionsPage.jsx";
import FlowPage from "../../pages/FlowPage.jsx";
import SettingsPage from "../../pages/SettingsPage.jsx";
import AuditPage from "../../pages/AuditPage.jsx";
import { CommandPalette } from "./command-palette.jsx";
import { Sidebar } from "./sidebar.jsx";
import { TitleBar } from "./titlebar.jsx";

const PAGE_TRANSITION = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -8 },
  transition: { duration: 0.18, ease: [0.16, 1, 0.3, 1] },
};

function AnimatedRoutes() {
  const location = useLocation();
  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div key={location.pathname} {...PAGE_TRANSITION} className="min-h-full">
        <Routes location={location}>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/editorial" element={<EditorialPage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/meetings" element={<MeetingsPage />} />
          <Route path="/works" element={<WorksPage />} />
          <Route path="/chapters" element={<ChaptersPage />} />
          <Route path="/reader" element={<ReaderPage />} />
          <Route path="/cost" element={<CostPage />} />
          <Route path="/executions" element={<ExecutionsPage />} />
          <Route path="/flow" element={<FlowPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/audit" element={<AuditPage />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </motion.div>
    </AnimatePresence>
  );
}

/** 应用壳：标题栏 + 五区导航 + 内容区 + 命令面板。@stable */
export function AppShell({ theme, onToggleTheme, onRefresh, schedulerOnline }) {
  return (
    <div className="flex h-screen flex-col bg-canvas text-ink">
      <TitleBar theme={theme} onToggleTheme={onToggleTheme} />
      <CommandPalette theme={theme} onToggleTheme={onToggleTheme} onRefresh={onRefresh} />
      <div className="flex min-h-0 flex-1">
        <Sidebar schedulerOnline={schedulerOnline} />
        <main className="min-w-0 flex-1 overflow-y-auto px-7 py-7 xl:px-9">
          <AnimatedRoutes />
        </main>
      </div>
    </div>
  );
}
