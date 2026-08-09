import { useEffect, useState } from "react";
import { getControl, postControl } from "../api.js";
import ReaderChart from "./ReaderChart.jsx";
import { ConfirmDialog, fmtRelative } from "./ui.jsx";

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

function WorkflowCard({ label, wf, onAction, onPause }) {
  const state = !wf?.online
    ? { text: "n8n 离线", cls: "chip-bad" }
    : wf.active
      ? { text: "● 运行中", cls: "chip-ok" }
      : { text: "● 已暂停", cls: "chip-bad" };
  const last = wf?.last
    ? `${wf.last.status} · ${fmtRelative(wf.last.stopped_at || wf.last.started_at)}`
    : "暂无执行记录";
  return (
    <div className="panel panel-hover p-4">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold">{label}</span>
        <span className={`chip ${state.cls}`}>{state.text}</span>
      </div>
      <div className="muted mt-1 text-xs">上次：{last}</div>
      <div className="mt-3 flex gap-2">
        {wf?.online && (
          wf.active ? (
            <button className="btn btn-danger !px-3 !py-1 text-xs" onClick={onPause}>
              暂停
            </button>
          ) : (
            <button className="btn btn-ok !px-3 !py-1 text-xs" onClick={() => onAction("resume")}>
              恢复
            </button>
          )
        )}
      </div>
    </div>
  );
}

export default function DashboardPage({ data, error, onRefresh, pushToast, snapshot }) {
  const [control, setControl] = useState(null);
  const [running, setRunning] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const [runChapters, setRunChapters] = useState(2);
  const [logDetail, setLogDetail] = useState(null);

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

  const s = data?.summary || {};
  const budget = data?.cost_budget ?? 100;
  const cost = s.monthly_cost ?? 0;
  const costPct = Math.min(100, Math.round((cost / budget) * 100));
  const passRate = s.quality_total ? Math.round((s.quality_passed / s.quality_total) * 100) : "—";
  const wfs = control?.workflows || {};
  const issues = data?.health?.issues || [];
  const liveIssueCount = snapshot?.issues ?? issues.length;
  const daily = wfs.daily || {};
  const liveExecs = snapshot?.executions || [];
  const runningNow = liveExecs.some((e) => e.status === "running" || e.status === "waiting");
  const lastExec = liveExecs[0];

  const today = new Date().toISOString().slice(0, 10);
  const todayPublished = (data?.chapters || []).filter(
    (c) => c.status === "published" && (c.published_at || "").slice(0, 10) === today,
  ).length;
  const todayFailed = (data?.publish_logs || []).filter(
    (l) => l.result === "failed" && (l.created_at || "").slice(0, 10) === today,
  ).length;

  const pipelineState = !daily.online
    ? { text: "n8n 离线", cls: "bad", desc: "工作流服务不可达，请检查 n8n 是否启动" }
    : runningNow
      ? { text: "流水线运行中", cls: "ok", desc: "正在后台生成并发布章节，可在执行记录查看进度" }
      : !daily.active
        ? { text: "日更已暂停", cls: "warn", desc: "定时更新已暂停，可到系统设置恢复" }
        : { text: "待命", cls: "ok", desc: `每日 ${control?.settings?.daily_run_time || "08:00"} 自动更新，可随时手动补更` };

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
                : lastExec
                  ? `今日尚未发布${todayFailed ? `，${todayFailed} 条发布失败待处理` : "，等待定时或手动触发"}`
                  : "今天还没有执行记录"}
            </div>
          </div>
          <div className="border-t border-[var(--line-soft)] p-5 md:border-l md:border-t-0">
            <div className="kpi-label">上次执行</div>
            <div className="mt-1 text-base font-semibold">
              {lastExec ? `${lastExec.workflow === "日更" ? "日更" : "周会"} · ${lastExec.status === "success" ? "成功" : lastExec.status === "running" ? "运行中" : "失败"}` : "暂无"}
            </div>
            <div className="muted mt-1.5 text-xs">
              {lastExec ? `${new Date(lastExec.started_at).toLocaleString("zh-CN", { hour12: false })}` : "运行后自动记录"}
            </div>
          </div>
        </div>
      </section>

      <div className="kpi-grid">
        <Kpi label="连载作品" value={s.novels ?? "—"} sub="全部连载中" />
        <Kpi label="章节总数" value={s.chapters_total ?? "—"} />
        <Kpi label="已发布" value={s.chapters_published ?? "—"} tone="ok" />
        <Kpi label="待发布" value={s.chapters_ready ?? "—"} tone="warn" />
        <Kpi label="草稿中" value={s.chapters_draft ?? "—"} />
        <Kpi label="质量通过率" value={`${passRate}%`} tone={s.quality_total && passRate < 70 ? "warn" : "ok"} />
        <Kpi label="发布失败" value={s.publish_failed ?? 0} tone={s.publish_failed ? "bad" : "ok"} />
        <Kpi label="本月成本" value={`¥${cost}`} sub={`预算 ¥${budget}`} tone={cost >= budget ? "bad" : "ok"} />
        <Kpi label="健康问题" value={liveIssueCount} tone={liveIssueCount ? "bad" : "ok"} />
      </div>

      <section>
        <div className="section-title">工作流状态</div>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <WorkflowCard label="日更工作流（56 节点）" wf={wfs.daily} onAction={(a) => action({ action: a, workflow: "daily" }, "日更已恢复")} onPause={() => setConfirm("pause-daily")} />
          <WorkflowCard label="架构师周会（6 节点）" wf={wfs.weekly} onAction={(a) => action({ action: a, workflow: "weekly" }, "周会已恢复")} onPause={() => setConfirm("pause-weekly")} />
          <div className="panel panel-hover p-4">
            <div className="text-sm font-semibold">手动补更</div>
            <div className="muted mt-1 text-xs">机器关机错过定时后，开机点这里立即执行完整日更（真实发布）</div>
            <button className="btn btn-ok mt-3" disabled={running} onClick={() => setConfirm("run")}>
              {running ? "正在启动…" : "▶ 立即补更"}
            </button>
          </div>
        </div>
      </section>

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

        <section className="panel p-4">
          <div className="section-title !mb-3">热点选题</div>
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
                    {src.error ? <span className="badge-bad"> · {src.error}</span> : ""}
                  </div>
              <div className="mt-0.5 break-words text-xs leading-relaxed text-slate-400">
                    {(src.titles || []).slice(0, 8).join("、")}
                  </div>
                </div>
              ))}
            </>
          ) : (
            <div className="empty">暂无热点数据，等待采集任务写入。</div>
          )}
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
        open={confirm === "pause-daily" || confirm === "pause-weekly"}
        title="暂停工作流？"
        body="暂停后定时触发将停止，需要手动恢复。"
        confirmText="暂停"
        onCancel={() => setConfirm(null)}
        onConfirm={() => {
          const workflow = confirm === "pause-daily" ? "daily" : "weekly";
          setConfirm(null);
          action({ action: "pause", workflow }, "已暂停");
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
