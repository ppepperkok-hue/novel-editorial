import { NavLink, Navigate, Outlet, Route, Routes } from "react-router-dom";

import OverviewPage from "./features/overview/OverviewPage";
import WorksCreatePage from "./features/works/WorksCreatePage";
import WorksDetailPage from "./features/works/WorksDetailPage";
import WorksListPage from "./features/works/WorksListPage";
import { useWorkspaceStore } from "./stores/workspaceStore";

function navClassName(isActive: boolean): string {
  return `app-nav-link${isActive ? " app-nav-link--active" : ""}`;
}

function Shell() {
  const currentWorkspace = useWorkspaceStore(
    (state) => state.currentWorkspace,
  );
  return (
    <div className="app">
      <aside className="app-sidebar">
        <div className="app-brand">Novel Editorial</div>
        <nav className="app-nav" aria-label="工作台">
          <NavLink to="/" end className={({ isActive }) => navClassName(isActive)}>
            总览
          </NavLink>
          <NavLink
            to="/works"
            end
            className={({ isActive }) => navClassName(isActive)}
          >
            作品与班子
          </NavLink>
        </nav>
      </aside>
      <div className="app-main">
        <header className="app-header">
          <h1>Novel Editorial</h1>
          {currentWorkspace !== null ? (
            <span className="header-workspace" data-testid="header-workspace">
              当前作品：{currentWorkspace.title}
            </span>
          ) : null}
        </header>
        <main className="app-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<OverviewPage />} />
        <Route path="works" element={<WorksListPage />} />
        <Route path="works/new" element={<WorksCreatePage />} />
        <Route path="works/:workspaceId" element={<WorksDetailPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
