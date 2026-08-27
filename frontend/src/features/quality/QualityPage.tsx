import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import type { UseMutationResult } from "@tanstack/react-query";

import type { CorpusPathBody, DraftSummary } from "../../api/client";
import { TextReportPanel } from "../../components/TextReportPanel";
import {
  EmptyState,
  ErrorState,
  SkeletonRows,
} from "../../components/StateViews";
import { useWorkspaceSelection } from "../../hooks/useWorkspaceSelection";
import {
  useCalibrateQuality,
  useDraftConsistency,
  useLearnStyle,
  useQualityCheck,
  useQualityDrafts,
  useQualityExplain,
  useQualityFeedback,
  useStyleDrift,
} from "./useQualityQueries";

function DraftRow({
  draft,
  selected,
  onSelect,
}: {
  draft: DraftSummary;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        className={`draft-list-item${selected ? " draft-list-item--selected" : ""}`}
        onClick={onSelect}
        data-testid={`quality-draft-${draft.id}`}
      >
        <span className="draft-list-title">{draft.title}</span>
        <span className="draft-list-meta">
          v{draft.current_version} · {draft.status}
        </span>
      </button>
    </li>
  );
}

function DraftSelector({
  workspaceId,
  selectedId,
  onSelect,
}: {
  workspaceId: string;
  selectedId: string | null;
  onSelect: (draftId: string | null) => void;
}) {
  const drafts = useQualityDrafts(workspaceId);
  return (
    <section className="panel quality-draft-selector" data-testid="quality-drafts">
      <header className="panel-header">
        <h3>草稿选择</h3>
      </header>
      <div className="panel-body">
        {drafts.isPending ? <SkeletonRows count={4} /> : null}
        {drafts.isError ? (
          <ErrorState
            source={`/works/${workspaceId}/drafts`}
            message={drafts.error.message}
            onRetry={() => void drafts.refetch()}
          />
        ) : null}
        {drafts.isSuccess && drafts.data.length === 0 ? (
          <EmptyState
            title="还没有草稿"
            hint="先在写作工作台产出正文，再回来打磨质量"
          />
        ) : null}
        {drafts.isSuccess && drafts.data.length > 0 ? (
          <ul className="draft-list" data-testid="quality-draft-list">
            {drafts.data.map((draft) => (
              <DraftRow
                key={draft.id}
                draft={draft}
                selected={draft.id === selectedId}
                onSelect={() =>
                  onSelect(draft.id === selectedId ? null : draft.id)
                }
              />
            ))}
          </ul>
        ) : null}
      </div>
    </section>
  );
}

function CorpusTool({
  title,
  hint,
  runLabel,
  dataTestId,
  mutation,
  applyNote,
}: {
  title: string;
  hint: string;
  runLabel: string;
  dataTestId: string;
  mutation: UseMutationResult<string, Error, CorpusPathBody, unknown>;
  applyNote?: string;
}) {
  const [path, setPath] = useState("");
  const [apply, setApply] = useState(false);
  const [applied, setApplied] = useState(false);

  function submit(event: FormEvent) {
    event.preventDefault();
    const trimmed = path.trim();
    if (trimmed === "") {
      return;
    }
    setApplied(false);
    mutation.mutate(
      { path: trimmed, apply },
      { onSuccess: () => setApplied(true) },
    );
  }

  return (
    <div className="corpus-tool" data-testid={dataTestId}>
      <h4>{title}</h4>
      <p className="form-hint">{hint}</p>
      <form className="corpus-form" onSubmit={submit}>
        <label className="form-field">
          <span className="form-label">语料路径</span>
          <input
            value={path}
            onChange={(event) => setPath(event.target.value)}
            placeholder="例如 data/corpus.txt"
            aria-label={`${title} 语料路径`}
          />
        </label>
        <label className="apply-check">
          <input
            type="checkbox"
            checked={apply}
            onChange={(event) => setApply(event.target.checked)}
            aria-label={`${title} apply`}
          />
          apply（写入配置 / 风格锚点）
        </label>
        <button
          type="submit"
          className="primary-button"
          disabled={path.trim() === "" || mutation.isPending}
        >
          {mutation.isPending ? "运行中…" : runLabel}
        </button>
      </form>
      {mutation.isError ? (
        <p className="inline-error" role="alert">
          运行失败：{mutation.error.message}
        </p>
      ) : null}
      {applied && apply && applyNote !== undefined ? (
        <p className="apply-note" data-testid={`${dataTestId}-apply-note`}>
          {applyNote}
        </p>
      ) : null}
      {mutation.data !== undefined ? (
        <pre className="plain-output" data-testid={`${dataTestId}-report`}>
          {mutation.data}
        </pre>
      ) : null}
    </div>
  );
}

function StylePanel({ workspaceId }: { workspaceId: string }) {
  const drift = useStyleDrift(workspaceId);
  const learn = useLearnStyle(workspaceId);
  return (
    <section className="panel style-panel" data-testid="style-panel">
      <header className="panel-header">
        <h3>风格</h3>
      </header>
      <div className="panel-body">
        <TextReportPanel
          title="风格漂移"
          source={`/works/${workspaceId}/style/drift`}
          query={drift}
          disabled={false}
          emptyTitle="暂无漂移报告"
          emptyHint="需要至少两章正文才能检测跨章节漂移"
          dataTestId="style-drift"
        />
        <CorpusTool
          title="文风学习（style learn）"
          hint="参考语料是服务所在机器的本地路径（localhost 语义）；apply 会把学到的风格描述写入作品风格锚点。"
          runLabel="学习并生成描述"
          dataTestId="style-learn"
          mutation={learn}
        />
      </div>
    </section>
  );
}

function CalibrationPanel() {
  const calibrate = useCalibrateQuality();
  const feedback = useQualityFeedback();
  return (
    <section className="panel calibration-panel" data-testid="calibration-panel">
      <header className="panel-header">
        <h3>校准与试读反馈</h3>
      </header>
      <div className="panel-body">
        <CorpusTool
          title="语料校准（quality calibrate）"
          hint="用一批已标注文本校准质量阈值；apply 会写入配置文件。"
          runLabel="运行校准"
          dataTestId="quality-calibrate"
          mutation={calibrate}
          applyNote="已写入配置文件，重启服务后生效"
        />
        <CorpusTool
          title="试读反馈（quality feedback）"
          hint="用试读者的好 / 坏反馈评估当前阈值；apply 会写入配置文件。"
          runLabel="分析反馈"
          dataTestId="quality-feedback"
          mutation={feedback}
          applyNote="已写入配置文件，重启服务后生效"
        />
      </div>
    </section>
  );
}

export default function QualityPage() {
  const { workspaceId } = useParams();
  useWorkspaceSelection(workspaceId);
  const workspaceIdValue = workspaceId ?? "";
  const [selectedDraftId, setSelectedDraftId] = useState<string | null>(null);

  useEffect(() => {
    setSelectedDraftId(null);
  }, [workspaceIdValue]);

  const check = useQualityCheck(workspaceIdValue, selectedDraftId);
  const explain = useQualityExplain(workspaceIdValue, selectedDraftId);
  const consistency = useDraftConsistency(workspaceIdValue, selectedDraftId);

  return (
    <section
      className="quality-page"
      data-testid="quality-page"
      data-workspace={workspaceId}
    >
      <header className="page-header">
        <h2>质量与风格</h2>
        <Link className="text-link" to={`/works/${workspaceIdValue}`}>
          返回作品
        </Link>
      </header>
      <DraftSelector
        workspaceId={workspaceIdValue}
        selectedId={selectedDraftId}
        onSelect={setSelectedDraftId}
      />
      <div className="quality-report-grid">
        <TextReportPanel
          title="质量门检查"
          source={`/works/${workspaceIdValue}/drafts/${selectedDraftId ?? ""}/quality/check`}
          query={check}
          disabled={selectedDraftId === null}
          emptyTitle="先选一篇草稿"
          emptyHint="选中草稿后自动运行质量门检查"
          dataTestId="quality-check"
        />
        <TextReportPanel
          title="AI 味定位与改写建议"
          source={`/works/${workspaceIdValue}/drafts/${selectedDraftId ?? ""}/quality/explain`}
          query={explain}
          disabled={selectedDraftId === null}
          emptyTitle="先选一篇草稿"
          emptyHint="好句块与改写建议会按 CLI 报告原样呈现"
          dataTestId="quality-explain"
        />
        <TextReportPanel
          title="一致性核查"
          source={`/works/${workspaceIdValue}/drafts/${selectedDraftId ?? ""}/consistency`}
          query={consistency}
          disabled={selectedDraftId === null}
          emptyTitle="先选一篇草稿"
          emptyHint="对照设定与伏笔检查矛盾"
          dataTestId="quality-consistency"
        />
      </div>
      <div className="quality-tools-layout">
        <StylePanel workspaceId={workspaceIdValue} />
        <CalibrationPanel />
      </div>
    </section>
  );
}
