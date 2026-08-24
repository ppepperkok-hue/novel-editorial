import { Link, useNavigate } from "react-router-dom";

import {
  EmptyState,
  ErrorState,
  SkeletonRows,
} from "../../components/StateViews";
import { formatDateTime } from "../../utils/format";
import { useWorks } from "./useWorksQueries";

export default function WorksListPage() {
  const works = useWorks();
  const navigate = useNavigate();

  return (
    <section className="works-page" data-testid="works-page">
      <header className="page-header">
        <h2>作品与班子</h2>
        <Link className="primary-button" to="/works/new">
          创建作品
        </Link>
      </header>
      {works.isPending ? <SkeletonRows count={4} /> : null}
      {works.isError ? (
        <ErrorState
          source="/works"
          message={works.error.message}
          onRetry={() => void works.refetch()}
        />
      ) : null}
      {works.isSuccess && works.data.length === 0 ? (
        <EmptyState
          title="还没有作品"
          hint="创建第一部作品，你的编辑部就会在这里开张"
        />
      ) : null}
      {works.isSuccess && works.data.length > 0 ? (
        <ul className="works-grid" data-testid="works-grid">
          {works.data.map((workspace) => (
            <li key={workspace.id}>
              <button
                type="button"
                className="works-card"
                onClick={() => navigate(`/works/${workspace.id}`)}
                data-testid="works-card"
              >
                <span className="works-card-title">{workspace.title}</span>
                <span className="works-card-meta">
                  类型：{workspace.genre || "未设定"}
                </span>
                <span className="works-card-meta">状态：{workspace.status}</span>
                <span className="works-card-meta">
                  创建：{formatDateTime(workspace.created_at)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
