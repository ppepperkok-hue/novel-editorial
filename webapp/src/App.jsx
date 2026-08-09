import { useCallback, useEffect, useState } from "react";
import { getDashboard } from "./api.js";
import ControlPanel from "./components/ControlPanel.jsx";
import WorksSection from "./components/WorksSection.jsx";
import ReaderChart from "./components/ReaderChart.jsx";

const statusCls = {
  draft: "badge-warn",
  reviewed: "badge-ok",
  queued: "badge-ok",
  published: "badge-ok",
  running: "badge-warn",
  failed: "badge-bad",
  pending: "badge-warn",
};

function Card({ label, value, cls }) {
  return (
    <div className="card">
      <div className="muted text-xs">{label}</div>
      <div className={`mt-1 text-xl font-semibold ${cls || ""}`}>{value}</div>
    </div>
  );
}

export default function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

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

  const s = data?.summary || {};
  const passRate = s.quality_total ? ((s.quality_passed / s.quality_total) * 100).toFixed(1) : "—";
  const cards = [
    ["小说", s.novels ?? "—", ""],
    ["章节总数", s.chapters_total ?? "—", ""],
    ["已发布", s.chapters_published ?? "—", "badge-ok"],
    ["待发布", s.chapters_ready ?? "—", "badge-warn"],
    ["草稿", s.chapters_draft ?? "—", "badge-warn"],
    ["质量通过率", passRate + "%", "badge-ok"],
    ["发布失败", s.publish_failed ?? 0, s.publish_failed ? "badge-bad" : "badge-ok"],
    [
      "本月成本",
      "¥" + (s.monthly_cost ?? 0) + " / " + (data?.cost_budget ?? 100),
      (s.monthly_cost ?? 0) >= (data?.cost_budget ?? 100) ? "badge-bad" : "badge-ok",
    ],
    [
      "健康问题",
      data?.health?.issues?.length ?? "—",
      data?.health?.issues?.length ? "badge-bad" : "badge-ok",
    ],
  ];

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">小说流水线控制台</h1>
          <div className="muted text-xs">更新于 {data?.updated_at || "—"}</div>
        </div>
        <button
          className="rounded-md border border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-800"
          onClick={refresh}
        >
          刷新
        </button>
      </header>

      {error ? (
        <div className="mb-4 rounded-md border border-red-900 bg-red-950/40 px-4 py-2 text-sm text-red-400">
          加载失败：{error}
        </div>
      ) : null}

      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {cards.map(([label, value, cls]) => (
          <Card key={label} label={label} value={value} cls={cls} />
        ))}
      </div>

      <div className="mb-6">
        <ControlPanel onChanged={refresh} />
      </div>

      <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="panel p-4">
          <h2 className="mb-2 text-sm font-semibold">健康检查</h2>
          {(data?.health?.issues || []).length ? (
            <ul className="list-disc pl-5 text-sm text-red-400">
              {(data.health.issues || []).map((i, k) => (
                <li key={k}>{i}</li>
              ))}
            </ul>
          ) : (
            <div className="badge-ok text-sm">● 全部正常</div>
          )}
          {data?.health?.log_tail?.length ? (
            <pre className="mt-2 max-h-40 overflow-auto rounded-md bg-slate-950 p-2 text-xs text-slate-400">
              {data.health.log_tail.join("\n")}
            </pre>
          ) : null}
        </div>

        <div className="panel p-4">
          <h2 className="mb-2 text-sm font-semibold">热点选题（网文榜单）</h2>
          {data?.hot_topics?.present ? (
            <>
              <div className="mb-2 flex flex-wrap gap-1.5">
                {(data.hot_topics.top_keywords || []).map(([k, n]) => (
                  <span key={k} className="rounded-full bg-slate-800 px-2 py-0.5 text-xs">
                    {k} ×{n}
                  </span>
                ))}
              </div>
              {(data.hot_topics.sources || []).map((src) => (
                <div key={src.source} className="mb-2">
                  <div className="muted text-xs">
                    {src.source}（{src.count || 0} 本）
                    {src.error ? ` · 抓取失败：${src.error}` : ""}
                  </div>
                  <div className="text-xs text-slate-400">
                    {(src.titles || []).slice(0, 10).join("、")}
                  </div>
                </div>
              ))}
            </>
          ) : (
            <div className="muted text-sm">暂无热点数据。</div>
          )}
        </div>
      </div>

      <section className="mb-6">
        <h2 className="mb-2 text-sm font-semibold">作品库</h2>
        <WorksSection novels={data?.novels} />
      </section>

      <section className="mb-6">
        <h2 className="mb-2 text-sm font-semibold">章节</h2>
        <div className="panel overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="muted border-b border-slate-800 text-left text-xs">
              <tr>
                <th className="px-3 py-2">ID</th>
                <th className="px-3 py-2">书ID</th>
                <th className="px-3 py-2">序号</th>
                <th className="px-3 py-2">标题</th>
                <th className="px-3 py-2">章纲</th>
                <th className="px-3 py-2">状态</th>
                <th className="px-3 py-2">字数</th>
                <th className="px-3 py-2">评分</th>
                <th className="px-3 py-2">番茄章节ID</th>
                <th className="px-3 py-2">发布时间</th>
              </tr>
            </thead>
            <tbody>
              {(data?.chapters || []).map((c) => (
                <tr key={c.id} className="border-b border-slate-800/60 last:border-0">
                  <td className="px-3 py-1.5">{c.id}</td>
                  <td className="px-3 py-1.5">{c.novel_id}</td>
                  <td className="px-3 py-1.5">{c.seq}</td>
                  <td className="px-3 py-1.5">{c.title}</td>
                  <td className="px-3 py-1.5 text-xs text-slate-400">{c.outline}</td>
                  <td className={`px-3 py-1.5 text-xs ${statusCls[c.status] || "badge-warn"}`}>
                    {c.status}
                  </td>
                  <td className="px-3 py-1.5">{c.words}</td>
                  <td className="px-3 py-1.5">{c.score ?? "—"}</td>
                  <td className="px-3 py-1.5 text-xs">{c.fanqie_item_id || "—"}</td>
                  <td className="px-3 py-1.5 text-xs">{c.published_at || "—"}</td>
                </tr>
              ))}
              {!(data?.chapters || []).length ? (
                <tr>
                  <td colSpan={10} className="px-3 py-4 text-center muted">暂无章节</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="panel p-4">
          <h2 className="mb-2 text-sm font-semibold">完读率 / 追读率</h2>
          <ReaderChart stats={data?.reader_stats} />
        </div>
        <div className="panel p-4">
          <h2 className="mb-2 text-sm font-semibold">发布日志（最近 20 条）</h2>
          <table className="w-full text-sm">
            <thead className="muted border-b border-slate-800 text-left text-xs">
              <tr>
                <th className="py-2 pr-3">章节</th>
                <th className="py-2 pr-3">平台</th>
                <th className="py-2 pr-3">动作</th>
                <th className="py-2 pr-3">结果</th>
                <th className="py-2">AI声明</th>
              </tr>
            </thead>
            <tbody>
              {(data?.publish_logs || []).slice(0, 20).map((l) => (
                <tr key={l.id} className="border-b border-slate-800/60 last:border-0">
                  <td className="py-1.5 pr-3">{l.chapter_id}</td>
                  <td className="py-1.5 pr-3">{l.platform}</td>
                  <td className="py-1.5 pr-3">{l.action}</td>
                  <td className={`py-1.5 pr-3 ${l.result === "failed" ? "badge-bad" : "badge-ok"}`}>
                    {l.result}
                  </td>
                  <td className="py-1.5">{l.ai_declared ? "是" : "否"}</td>
                </tr>
              ))}
              {!(data?.publish_logs || []).length ? (
                <tr>
                  <td colSpan={5} className="py-4 text-center muted">暂无发布日志</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
