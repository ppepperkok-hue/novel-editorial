import { getControl, getDashboard, getKnowledgeDrafts, getMeetings } from "../api.js";
import { DashboardSide } from "../components/features/dashboard/dashboard-side.jsx";
import { OpenWorkday } from "../components/features/dashboard/open-workday.jsx";
import { StatusBand } from "../components/features/dashboard/status-band.jsx";
import { TodayTimeline } from "../components/features/dashboard/today-timeline.jsx";
import { PageHeader } from "../components/layout/page-header.jsx";
import { ErrorState } from "../components/features/states.jsx";
import { useApi } from "../lib/use-api.js";

function localToday() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** 仪表盘：编辑部工作台首页。@stable */
export default function DashboardPage() {
  const { data, error, refresh } = useApi(getDashboard, { interval: 10000 });
  const { data: control } = useApi(getControl, { interval: 30000 });
  const { data: meetingsData } = useApi(getMeetings, { interval: 60000 });
  const { data: draftsData } = useApi(() => getKnowledgeDrafts("draft"), { interval: 60000 });

  const summary = data?.summary || {};
  const today = localToday();
  const todayPublished = (data?.chapters || []).filter(
    (c) => c.status === "published" && String(c.published_at || "").slice(0, 10) === today,
  ).length;
  const todayFailed = (data?.publish_logs || []).filter(
    (l) => l.result === "failed" && String(l.created_at || "").slice(0, 10) === today,
  ).length;

  const sch = control?.scheduler || null;
  const lastRun = sch?.last_run || data?.executions?.[0] || null;
  const workdayRow = sch?.workday || null;
  const awaitingClose = workdayRow?.phase === "awaiting_close";
  const budget = data?.cost_budget ?? 100;

  return (
    <>
      <PageHeader title="仪表盘" desc="编辑部现在的状态，和需要您留意的事" />
      {error ? (
        <ErrorState message="后端连接失败" detail={error} onRetry={refresh} className="mb-5" />
      ) : (
        <StatusBand
          scheduler={sch}
          summary={summary}
          todayPublished={todayPublished}
          todayFailed={todayFailed}
          lastRun={lastRun}
        />
      )}

      <div className="grid grid-cols-1 gap-7 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-7">
          <OpenWorkday workday={workdayRow} onChanged={refresh} />
          <section className="min-w-0">
            <div className="mb-3 flex items-baseline justify-between">
              <h2 className="text-xs font-semibold tracking-[0.02em] text-ink">今日记录</h2>
              <a href="#/executions" className="text-xs text-accent-ink hover:underline">
                全部执行记录
              </a>
            </div>
            <TodayTimeline publishLogs={data?.publish_logs} executions={data?.executions} />
          </section>
        </div>
        <DashboardSide
          data={data}
          drafts={draftsData?.drafts}
          meeting={meetingsData?.meetings?.[0]}
          workdayAwaiting={awaitingClose}
          budget={budget}
        />
      </div>
    </>
  );
}
