import { Fragment, useMemo, useState } from "react";
import { fmtNum } from "./ui.jsx";

const STATUS_META = {
  draft: ["草稿", "chip-warn"],
  reviewed: ["已审稿", "chip-ok"],
  queued: ["待发布", "chip-info"],
  publishing: ["发布中", "chip-warn"],
  published: ["已发布", "chip-ok"],
  failed: ["失败", "chip-bad"],
};

export default function ChaptersPage({ data }) {
  const [filter, setFilter] = useState("all");
  const [novelFilter, setNovelFilter] = useState("all");
  const [expanded, setExpanded] = useState(null);

  const novels = data?.novels || [];
  const chapters = (data?.chapters || []).filter((c) => {
    if (novelFilter !== "all" && String(c.novel_id) !== novelFilter) return false;
    if (filter !== "all" && c.status !== filter) return false;
    return true;
  });

  const counts = useMemo(() => {
    const map = {};
    for (const c of data?.chapters || []) map[c.status] = (map[c.status] || 0) + 1;
    return map;
  }, [data]);

  const titleFor = (novelId) => novels.find((n) => String(n.id) === String(novelId))?.title || `书 ${novelId}`;

  const stats = useMemo(() => {
    const list = data?.chapters || [];
    return {
      total: list.length,
      words: list.reduce((a, c) => a + Number(c.words || 0), 0),
      scored: list.filter((c) => c.score != null).length,
      avg: (() => {
        const scored = list.filter((c) => c.score != null);
        return scored.length ? (scored.reduce((a, c) => a + Number(c.score || 0), 0) / scored.length).toFixed(1) : "—";
      })(),
    };
  }, [data]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="chip" onClick={() => setFilter("all")} style={{ cursor: "pointer" }}>全部 {data?.chapters?.length || 0}</span>
        {Object.entries(STATUS_META).map(([st, [label, cls]]) => (
          <span key={st} className={`chip ${cls} ${filter === st ? "!border-[#5ba4d4] !text-[#7db9dd]" : ""}`} onClick={() => setFilter(st)} style={{ cursor: "pointer" }}>
            {label} {counts[st] || 0}
          </span>
        ))}
        <select className="input ml-auto !w-auto" value={novelFilter} onChange={(e) => setNovelFilter(e.target.value)}>
          <option value="all">全部作品</option>
          {novels.map((n) => (
            <option key={n.id} value={String(n.id)}>{n.title}</option>
          ))}
        </select>
      </div>

      <div className="kpi-grid !grid-cols-2 lg:!grid-cols-4">
        <div className="card kpi">
          <div className="kpi-label">当前筛选章节</div>
          <div className="kpi-value">{chapters.length}</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">筛选字数合计</div>
          <div className="kpi-value">{fmtNum(chapters.reduce((a, c) => a + Number(c.words || 0), 0))}</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">已评分 / 平均分</div>
          <div className="kpi-value">{stats.avg} <span className="text-sm muted">/ {stats.scored}</span></div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">全部章节</div>
          <div className="kpi-value">{stats.total}</div>
        </div>
      </div>

      <div className="panel overflow-hidden">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>作品</th>
                <th>序号</th>
                <th>标题</th>
                <th>状态</th>
                <th>字数</th>
                <th>评分</th>
                <th>修订</th>
                <th>番茄章节 ID</th>
                <th>发布时间</th>
              </tr>
            </thead>
            <tbody>
              {chapters.map((c) => (
                <Fragment key={c.id}>
                  <tr className="cursor-pointer" onClick={() => setExpanded(expanded === c.id ? null : c.id)}>
                    <td className="muted">{c.id}</td>
                    <td className="text-sky-400">{titleFor(c.novel_id)}</td>
                    <td>{c.seq}</td>
                    <td className="font-medium">{c.title || "（无标题）"}</td>
                    <td>
                      <span className={`chip ${(STATUS_META[c.status] || ["未知", "chip-warn"])[1]}`}>
                        {(STATUS_META[c.status] || ["未知", "chip-warn"])[0]}
                      </span>
                    </td>
                    <td className="tabular-nums">{c.words ?? "—"}</td>
                    <td className={c.score == null ? "" : c.score >= 80 ? "badge-ok" : c.score >= 60 ? "badge-warn" : "badge-bad"}>
                      {c.score ?? "—"}
                    </td>
                    <td>{c.revisions ?? 0}</td>
                    <td className="code text-xs">{c.fanqie_item_id || "—"}</td>
                    <td className="muted text-xs">{c.published_at || "—"}</td>
                  </tr>
                  {expanded === c.id ? (
                    <tr>
                      <td colSpan={10} className="!bg-[#0a0f18]">
                        <div className="px-3 py-3">
                          <div className="label">章节大纲</div>
                          <div className="text-sm leading-relaxed text-slate-300">{c.outline || "无章纲"}</div>
                        </div>
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              ))}
              {!chapters.length ? (
                <tr><td colSpan={10} className="empty">没有符合条件的章节</td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
