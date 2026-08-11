import { useEffect, useState } from "react";
import { getControl, postControl, refreshHotTopics } from "../api.js";
import ReaderChart from "./ReaderChart.jsx";
import { ConfirmDialog, fmtTime } from "./ui.jsx";
import { getMeetings } from "../api.js";

export function localToday() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function Kpi({ label, value, sub, tone }) {
  return (
    <div className="card kpi">
      <div className="kpi-label">{label}</div>
      <div className={`kpi-value ${tone === "ok" ? "badge-ok" : tone === "bad" ? "badge-bad" : tone === "warn" ? "badge-warn" : ""}`}>
        {value}
      </div>
      {sub ? <div className="kpi-sub">{sub}</div> : null}
    </div>
  );
}

function ProcessCard({ title, badge, badgeCls, desc, children }) {
  return (
    <div className="panel panel-hover p-4">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold">{title}</span>
        <span className={`chip ${badgeCls}`}>{badge}</span>
      </div>
      <div className="muted mt-1 text-xs">{desc}</div>
      <div className="mt-3 flex flex-wrap gap-2">{children}</div>
    </div>
  );
}

export default function DashboardPage({ data, error, onRefresh, pushToast, snapshot }) {
  const [control, setControl] = useState(null);
  const [running, setRunning] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const [runChapters, setRunChapters] = useState(2);
  const [logDetail, setLogDetail] = useState(null);
  const [latestMeeting, setLatestMeeting] = useState(null);
  const [hotBusy, setHotBusy] = useState(false);

  const refreshControl = async () => {
    try {
      setControl(await getControl());
    } catch {
      setControl(null);
    }
  };

  useEffect(() => {
    refreshControl();
    const t = setInterval(refreshControl, 30000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    const load = () => {
      getMeetings()
        .then((r) => setLatestMeeting(r.meetings?.[0] || null))
        .catch(() => {});
    };
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, []);

  const action = async (payload, okMsg) => {
    const r = await postControl(payload);
    pushToast(r.ok ? okMsg : `失败：${r.error || "未知"}`, r.ok ? "ok" : "bad");
    refreshControl();
    onRefresh();
  };

  const runNow = async (chapters) => {
    setRunning(true);
    setConfirm(null);
    setRunChapters(2);
    try {
      const r = await postControl({ action: "run_now", workflow: "daily", chapters });
      pushToast(
        r.ok
          ? `已启动：本次目标发布 ${chapters} 章（存稿优先）`
          : "启动失败：" + (r.error || "未知"),
        r.ok ? "ok" : "bad",
      );
      refreshControl();
      onRefresh();
    } finally {
      setRunning(false);
    }
  };

  const collectHot = async () => {
    setHotBusy(true);
    try {
      const r = await refreshHotTopics();
      pushToast(
        r.ok
          ? `热点采集完成（${(r.sources || []).filter((s) => s.count > 0).length}/${(r.sources || []).length} 源成功）`
          : "热点采集失败：" + (r.error || "未知"),
        r.ok ? "ok" : "bad",
      );
      onRefresh();
    } finally {
      setHotBusy(false);
    }
  };

  const s = data?.summary || {};
  const budget = data?.cost_budget ?? 100;
  const cost = s.monthly_cost ?? 0;
  const costPct = Math.min(100, Math.round((cost / budget) * 100));
  const passRate = s.quality_total ? Math.round((s.quality_passed / s.quality_total) * 100) : "—";
  const issues = data?.health?.issues || [];
  const liveIssueCount = snapshot?.issues ?? issues.length;
  const liveExecs = snapshot?.executions || data?.executions || [];
  const runningNow = liveExecs.some((e) => e.status === "running" || e.status === "waiting");
  const sch = control?.scheduler || null;
  const lastRun = sch?.last_run || null;
  const lastExec = lastRun
    ? {
        workflow: "日更",
        status: lastRun.status,
        started_at: lastRun.started_at,
        stopped_at: lastRun.finished_at,
      }
    : liveExecs[0] || null;
  const runStatusText = {
    completed: "成功",
    success: "成功",
    partial: "部分成功",
    running: "运行中",
    failed: "失败",
    error: "失败",
    crashed: "崩溃",
  }[lastExec?.status] || lastExec?.status || "未知";

  const today = localToday();
  const todayPublished = (data?.chapters || []).filter(
    (c) => c.status === "published" && (c.published_at || "").slice(0, 10) === today,
  ).length;
  const todayFailed = (data?.publish_logs || []).filter(
    (l) => l.result === "failed" && (l.created_at || "").slice(0, 10) === today,
  ).length;

  const pipelineState = !sch
    ? { text: "调度器未知", cls: "bad", desc: "无法读取调度器状态，请检查后端服务" }
    : runningNow || lastRun?.status === "running"
      ? { text: "流水线运行中", cls: "ok", desc: "正在后台生成并发布章节，可在执行记录查看进度" }
      : !sch.enabled
        ? { text: "日更已暂停", cls: "warn", desc: "定时与手动日更已暂停，点击日更卡片恢复" }
        : lastRun?.status === "failed"
          ? { text: "待命 · 上次失败", cls: "warn", desc: `上次运行失败：${(lastRun.error || "无详情").slice(0, 60)}` }
          : lastRun?.status === "partial"
            ? { text: "待命 · 上次部分成功", cls: "warn", desc: `上次发布 ${lastRun.published ?? 0} 章，存在失败节点待处理` }
            : { text: "待命", cls: "ok", desc: `每日 ${sch.scheduled_time || "08:00"} 自动更新，可随时手动补更` };

  const stateDot = { ok: "online", bad: "offline", warn: "paused" }[pipelineState.cls];

  return (
    <div className="flex flex-col gap-6">
      {error ? (
        <div className="rounded-lg border border-red-900 bg-red-950/40 px-4 py-2.5 text-sm text-red-400">
          后端连接失败：{error}
        </div>
      ) : null}

      <section className="panel overflow-hidden">
        <div className="grid grid-cols-1 gap-0 md:grid-cols-[1.2fr_1fr_1fr]">
          <div className="flex items-center gap-4 p-5">
            <span className={`status-dot ${stateDot} !h-4 !w-4`} />
            <div>
              <div className={`text-xl font-bold ${pipelineState.cls === "bad" ? "badge-bad" : pipelineState.cls === "warn" ? "badge-warn" : "badge-ok"}`}>
                {pipelineState.text}
              </div>
              <div className="muted mt-1 text-xs leading-relaxed">{pipelineState.desc}</div>
            </div>
          </div>
          <div className="border-t border-[var(--line-soft)] p-5 md:border-l md:border-t-0">
            <div className="kpi-label">今日任务</div>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="text-2xl font-bold">{todayPublished}</span>
              <span className="muted text-xs">章已发布</span>
            </div>
            <div className="muted mt-1.5 text-xs">
              {todayPublished > 0
                ? `今天已完成日更${todayFailed ? `，另有 ${todayFailed} 条发布失败` : ""}`
                : lastRun
                  ? `今日尚未发布${todayFailed ? `，${todayFailed} 条发布失败待处理` : "，等待定时或手动触发"}`
                  : "今天还没有执行记录"}
            </div>
          </div>
          <div className="border-t border-[var(--line-soft)] p-5 md:border-l md:border-t-0">
            <div className="kpi-label">上次执行</div>
            <div className="mt-1 text-base font-semibold">
              {lastExec ? `${lastExec.workflow === "日更" ? "日更" : "周会"} · ${runStatusText}` : "暂无"}
            </div>
            <div className="muted mt-1.5 text-xs">
              {lastExec ? `${new Date(lastExec.started_at).toLocaleString("zh-CN", { hour12: false })}` : "运行后自动记录"}
            </div>
          </div>
        </div>
      </section>

      {latestMeeting ? (
        <section className="panel p-4">
          <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
            <span className="text-xs font-semibold">最近会议</span>
            <span className="chip">#{latestMeeting.id}</span>
            <span className="muted text-xs">{fmtTime(latestMeeting.held_at)}</span>
            <span className="muted text-xs">参会：{latestMeeting.attendees.join("、")}</span>
            <a className="btn ml-auto !px-3 !py-1 text-xs" href="#meetings">▦ 打开会议中心</a>
          </div>
          <div className="muted text-xs leading-relaxed">{latestMeeting.summary}</div>
        </section>
      ) : (
        <section className="panel p-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold">会议中心</span>
            <a className="btn ml-auto !px-3 !py-1 text-xs" href="#meetings">▦ 发起专题会议</a>
          </div>
          <div className="muted mt-1.5 text-xs">还没有会议记录，去会议中心让 Agent 们开一场吧。</div>
        </section>
      )}

      <section>
        <div className="mb-3 flex items-center justify-between">
          <div className="section-title !mb-0">流程状态与补更</div>
          <a className="btn !px-3 !py-1 text-xs" href="#flow">⬡ 打开链路视图</a>
        </div>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <ProcessCard
            title="日更调度"
            badge={sch?.enabled ? "● 已开启" : "● 已暂停"}
            badgeCls={sch?.enabled ? "chip-ok" : "chip-bad"}
            desc={
              lastRun
                ? `定时 ${sch?.scheduled_time || "08:00"} · 上次${runStatusText} · 发布 ${lastRun.published ?? 0} 章`
                : `定时 ${sch?.scheduled_time || "08:00"} · 暂无执行记录`
            }
          >
            {sch?.enabled ? (
              <button className="btn btn-danger !px-3 !py-1 text-xs" onClick={() => setConfirm("pause-daily")}>
                暂停
              </button>
            ) : (
              <button className="btn btn-ok !px-3 !py-1 text-xs" onClick={() => action({ action: "resume", workflow: "daily" }, "日更已恢复")}>
                恢复
              </button>
            )}
          </ProcessCard>
          <ProcessCard
            title="架构师周会"
            badge="手动触发"
            badgeCls="chip-warn"
            desc="后台依次执行：采集热点 → 读上下文 → 开会 → 蒸馏经验"
          >
            <button className="btn !px-3 !py-1 text-xs" onClick={() => action({ action: "run_now", workflow: "weekly" }, "周会已启动")}>
              ▶ 立即开会
            </button>
          </ProcessCard>
          <ProcessCard
            title="知识管家"
            badge="手动触发"
            badgeCls="chip-warn"
            desc="维护热点市场包与知识库草案，规则型变更需人工采纳"
          >
            <button className="btn !px-3 !py-1 text-xs" onClick={() => action({ action: "run_knowledge_keeper" }, "知识管家已运行")}>
              ▶ 立即维护
            </button>
          </ProcessCard>
          <div className="panel panel-hover p-4">
            <div className="text-sm font-semibold">手动补更</div>
            <div className="muted mt-1 text-xs">存稿优先：有存货直接发，不够自动补造并发布</div>
            <button className="btn btn-ok mt-3" disabled={running} onClick={() => setConfirm("run")}>
              {running ? "正在启动…" : "▶ 立即补更"}
            </button>
          </div>
        </div>
      </section>

      <div className="kpi-grid">
        <Kpi label="连载作品" value={s.novels ?? "—"} />
        <Kpi label="章节总数" value={s.chapters_total ?? "—"} />
        <Kpi label="已发布" value={s.chapters_published ?? "—"} tone="ok" />
        <Kpi label="待发布" value={s.chapters_ready ?? "—"} tone="warn" />
        <Kpi label="草稿中" value={s.chapters_draft ?? "—"} />
        <Kpi label="质量通过率" value={`${passRate}%`} tone={s.quality_total && passRate < 70 ? "warn" : "ok"} />
        <Kpi label="发布失败" value={s.publish_failed ?? 0} tone={s.publish_failed ? "bad" : "ok"} />
        <Kpi label="本月成本" value={`¥${cost}`} sub={`预算 ¥${budget}`} tone={cost >= budget ? "bad" : "ok"} />
        <Kpi label="健康问题" value={liveIssueCount} tone={liveIssueCount ? "bad" : "ok"} />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <section className="panel p-4">
          <div className="section-title !mb-3">月度预算</div>
          <div className="mb-2 flex items-baseline justify-between">
            <span className="text-2xl font-bold">¥{cost}</span>
            <span className="muted text-xs">/ ¥{budget} · {costPct}%</span>
          </div>
          <div className={`progress ${cost >= budget ? "bad" : cost / budget > 0.7 ? "warn" : ""}`}>
            <div style={{ width: `${costPct}%` }} />
          </div>
          <div className="muted mt-3 text-xs leading-relaxed">
            预算来自系统设置，可到「系统设置」调整。成本按日与节点明细见「成本中心」。
          </div>
        </section>

        <section className="panel p-4">
          <div className="section-title !mb-3">健康检查</div>
          {issues.length ? (
            <ul className="flex flex-col gap-1.5 text-sm text-red-400">
              {issues.map((i, k) => (
                <li key={k} className="break-words rounded-md bg-red-950/30 px-2.5 py-1.5 leading-relaxed">● {i}</li>
              ))}
            </ul>
          ) : (
            <div className="flex items-center gap-2 text-sm text-emerald-400">
              <span className="status-dot online" /> 全部正常，无需干预
            </div>
          )}
          {data?.health?.log_tail?.length ? (
            <details className="mt-3">
              <summary className="cursor-pointer text-xs text-sky-400">查看最近告警日志（{data.health.log_tail.length} 条）</summary>
              <pre className="code mt-2 max-h-44 overflow-auto rounded-lg bg-[var(--code-bg)] p-2.5 text-xs leading-relaxed text-slate-400">
                {data.health.log_tail.join("\n")}
              </pre>
            </details>
          ) : null}
        </section>

      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <section className="panel p-4">
          <div className="section-title !mb-3">完读率 / 追读率</div>
          <ReaderChart stats={data?.reader_stats} />
        </section>

        <section className="panel p-4">
          <div className="section-title !mb-3">最近发布（20 条）</div>
          <div className="table-wrap max-h-72 overflow-y-auto">
            <table>
              <thead>
                <tr>
                  <th>章节</th>
                  <th>平台</th>
                  <th>动作</th>
                  <th>结果</th>
                  <th>AI 声明</th>
                </tr>
              </thead>
              <tbody>
                {(data?.publish_logs || []).slice(0, 20).map((l) => (
                  <tr key={l.id} className={l.error ? "cursor-pointer" : ""} onClick={l.error ? () => setLogDetail(l) : undefined} title={l.error ? "点击查看错误详情" : undefined}>
                    <td>#{l.chapter_id}</td>
                    <td>{l.platform}</td>
                    <td>{l.action}</td>
                    <td>
                      <span className={`chip ${l.result === "failed" ? "chip-bad" : "chip-ok"}`}>{l.result}</span>
                    </td>
                    <td>{l.ai_declared ? "是" : "否"}</td>
                  </tr>
                ))}
                {!(data?.publish_logs || []).length ? (
                  <tr><td colSpan={5} className="empty">暂无发布记录</td></tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <section className="panel p-4">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <div className="section-title !mb-0">热点选题</div>
          <span className="muted text-xs">{data?.hot_topics?.updated_at ? `更新于 ${data.hot_topics.updated_at}` : ""}</span>
          <button className="btn ml-auto !px-3 !py-1 text-xs" disabled={hotBusy} onClick={collectHot}>
            {hotBusy ? "采集中…" : "⇅ 立即采集"}
          </button>
        </div>
        {data?.hot_topics?.present ? (
          <>
            <div className="mb-2 flex flex-wrap gap-1.5">
              {(data.hot_topics.top_keywords || []).map(([k, n]) => (
                <span key={k} className="chip chip-info">{k} ×{n}</span>
              ))}
            </div>
            {(data.hot_topics.sources || []).map((src) => (
              <div key={src.source} className="mb-2">
                <div className="muted text-xs">
                  {src.source}（{src.count || 0} 本）
                  {src.method ? <span className={`chip ml-1 !px-1.5 !py-0.5 ${src.method === "html" ? "chip-ok" : src.method === "browser" ? "chip-warn" : "chip-bad"}`}>{src.method}</span> : ""}
                  {src.error ? <span className="badge-bad"> · {src.error}</span> : ""}
                </div>
                {(src.books || []).length ? (
                  <div className="mt-1 flex flex-col gap-1">
                    {(src.books || []).slice(0, 8).map((b) => (
                      <div key={b.url || b.title} className="rounded-md bg-[var(--bg-soft)] px-2 py-1.5">
                        <div className="text-xs text-slate-300">
                          <span className="font-semibold">{b.title}</span>
                          {b.author ? <span className="muted"> · {b.author}</span> : ""}
                          {b.latest ? <span className="muted"> · {b.latest}</span> : ""}
                        </div>
                        {b.intro ? (
                          <div className="muted mt-0.5 break-words text-xs leading-relaxed">{b.intro}</div>
                        ) : null}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="mt-0.5 break-words text-xs leading-relaxed text-slate-400">
                    {(src.titles || []).slice(0, 8).join("、")}
                  </div>
                )}
              </div>
            ))}
          </>
        ) : (
          <div className="empty">暂无热点数据，等待采集任务写入。</div>
        )}
      </section>

      {confirm === "run" ? (
        <div className="modal-mask" onMouseDown={(e) => e.target === e.currentTarget && setConfirm(null)}>
          <div className="modal confirm-modal">
            <div className="modal-head">
              <div className="text-sm font-bold">本次发布几章？</div>
              <button className="btn !px-2 !py-0.5 text-sm" onClick={() => setConfirm(null)}>✕</button>
            </div>
            <div className="modal-body">
              <div className="mb-4 text-sm text-slate-400">
                存稿池有存货就直接发，不够会自动补造。最多一次发 5 章。
              </div>
              <div className="flex gap-2">
                {[1, 2, 3, 4, 5].map((n) => (
                  <button
                    key={n}
                    className={`btn flex-1 !py-3 text-base ${runChapters === n ? "btn-primary" : ""}`}
                    onClick={() => setRunChapters(n)}
                  >
                    {n} 章
                  </button>
                ))}
              </div>
              <div className="mt-5 flex justify-end gap-2">
                <button className="btn" onClick={() => setConfirm(null)}>取消</button>
                <button className="btn btn-ok" disabled={running} onClick={() => runNow(runChapters)}>
                  发布 {runChapters} 章
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      <ConfirmDialog
        open={confirm === "pause-daily"}
        title="暂停日更调度？"
        body="暂停后定时与手动补更都会停止，需要手动恢复。"
        confirmText="暂停"
        onCancel={() => setConfirm(null)}
        onConfirm={() => {
          setConfirm(null);
          action({ action: "pause", workflow: "daily" }, "日更已暂停");
        }}
      />

      {logDetail ? (
        <div className="modal-mask" onMouseDown={(e) => e.target === e.currentTarget && setLogDetail(null)}>
          <div className="modal confirm-modal">
            <div className="modal-head">
              <div className="text-sm font-bold">发布失败详情 #{logDetail.chapter_id}</div>
              <button className="btn !px-2 !py-0.5 text-sm" onClick={() => setLogDetail(null)}>✕</button>
            </div>
            <div className="modal-body">
              <div className="mb-2 text-xs text-slate-400">
                {logDetail.platform} · {logDetail.action} · {logDetail.result}
              </div>
              <pre className="code max-h-72 overflow-auto rounded-lg bg-[var(--code-bg)] p-3 text-xs leading-relaxed text-red-300">
                {logDetail.error}
              </pre>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
