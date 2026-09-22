import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import {
  exportWorkspace,
  importWorkspace,
  type WorkspaceSummary,
} from "../../api/client";
import { ErrorState, SkeletonRows } from "../../components/StateViews";
import { useWorkspaceSelection } from "../../hooks/useWorkspaceSelection";
import { useConfigSnapshot, useUpdateConfig } from "./useDataQueries";

const WRITABLE_KEYS = [
  "quality_threshold",
  "panel_poll_interval",
  "freedom_dial",
  "freedom_seed",
  "proactive_enabled",
  "proactive_max_per_agent",
  "motive_llm_enabled",
] as const;

type WritableKey = (typeof WRITABLE_KEYS)[number];

const WRITABLE_KEY_LABELS: Record<WritableKey, string> = {
  quality_threshold: "质量门阈值 quality_threshold",
  panel_poll_interval: "轮询间隔 panel_poll_interval",
  freedom_dial: "自由意志拨盘 freedom_dial",
  freedom_seed: "自由意志种子 freedom_seed",
  proactive_enabled: "主动行为 proactive_enabled",
  proactive_max_per_agent: "主动上限 proactive_max_per_agent",
  motive_llm_enabled: "动机 LLM motive_llm_enabled",
};

const BOOL_KEYS = new Set<WritableKey>([
  "proactive_enabled",
  "motive_llm_enabled",
]);

const FLOAT_KEYS = new Set<WritableKey>(["freedom_dial"]);

interface IntRule {
  min?: number;
  max?: number;
  message: string;
}

type IntKey = Exclude<
  WritableKey,
  "freedom_dial" | "proactive_enabled" | "motive_llm_enabled"
>;

const INT_KEY_RULES: Record<IntKey, IntRule> = {
  quality_threshold: {
    min: 0,
    message: "quality_threshold 必须是 ≥0 的整数",
  },
  panel_poll_interval: {
    min: 1,
    max: 300,
    message: "panel_poll_interval 必须是 1–300 的整数",
  },
  freedom_seed: {
    message: "freedom_seed 必须是整数",
  },
  proactive_max_per_agent: {
    min: 0,
    message: "proactive_max_per_agent 必须是 ≥0 的整数",
  },
};

type ConfigValidation =
  | { ok: true; value: number | boolean }
  | { ok: false; message: string };

function validateConfigValue(key: WritableKey, raw: string): ConfigValidation {
  if (BOOL_KEYS.has(key)) {
    return { ok: true, value: raw === "true" };
  }
  if (FLOAT_KEYS.has(key)) {
    const parsed = Number(raw);
    if (Number.isNaN(parsed) || parsed < 0 || parsed > 1) {
      return { ok: false, message: "freedom_dial 必须是 0–1 之间的数值" };
    }
    return { ok: true, value: parsed };
  }
  const rule = INT_KEY_RULES[key as IntKey];
  const parsed = Number(raw);
  if (!Number.isInteger(parsed)) {
    return { ok: false, message: rule.message };
  }
  if (rule.min !== undefined && parsed < rule.min) {
    return { ok: false, message: rule.message };
  }
  if (rule.max !== undefined && parsed > rule.max) {
    return { ok: false, message: rule.message };
  }
  return { ok: true, value: parsed };
}

function ExportPanel({ workspaceId }: { workspaceId: string }) {
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runExport() {
    setExporting(true);
    setError(null);
    try {
      await exportWorkspace(workspaceId);
    } catch (exportError) {
      setError(
        exportError instanceof Error ? exportError.message : String(exportError),
      );
    } finally {
      setExporting(false);
    }
  }

  return (
    <section className="panel data-panel" data-testid="export-panel">
      <header className="panel-header">
        <h3>导出</h3>
      </header>
      <div className="panel-body">
        <p className="panel-hint">
          把整部作品（班子、草稿、设定、意见、日志）打包成可校验的 ZIP；
          导出 ZIP 即本地备份留档，文件名含日期。
        </p>
        <button
          type="button"
          className="primary-button"
          onClick={() => void runExport()}
          disabled={exporting}
        >
          {exporting ? "导出中…" : "导出 ZIP"}
        </button>
        {error ? (
          <p className="inline-error" role="alert">
            导出失败：{error}
          </p>
        ) : null}
      </div>
    </section>
  );
}

function ImportPanel() {
  const [file, setFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<WorkspaceSummary | null>(null);

  async function runImport() {
    if (file === null) {
      return;
    }
    setImporting(true);
    setError(null);
    setResult(null);
    try {
      const workspace = await importWorkspace(file);
      setResult(workspace);
    } catch (importError) {
      setError(
        importError instanceof Error ? importError.message : String(importError),
      );
    } finally {
      setImporting(false);
    }
  }

  return (
    <section className="panel data-panel" data-testid="import-panel">
      <header className="panel-header">
        <h3>导入</h3>
      </header>
      <div className="panel-body">
        <p className="panel-hint">
          上传之前导出的 ZIP，作为一部全新作品导入，不会覆盖现有作品。
        </p>
        <label className="file-picker">
          <input
            type="file"
            accept=".zip"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            data-testid="import-file-input"
            aria-label="选择 ZIP 文件"
          />
          <span className="file-picker-face">
            {file === null ? "选择 ZIP 文件" : file.name}
          </span>
        </label>
        <button
          type="button"
          className="primary-button"
          onClick={() => void runImport()}
          disabled={file === null || importing}
        >
          {importing ? "导入中…" : "导入"}
        </button>
        {error ? (
          <p className="inline-error" role="alert">
            导入失败：{error}
          </p>
        ) : null}
        {result !== null ? (
          <div className="import-result" data-testid="import-result">
            <p>已导入作品：{result.title}</p>
            <p className="import-result-id">ID：{result.id}</p>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function ConfigPanel() {
  const config = useConfigSnapshot();
  const update = useUpdateConfig();
  const [selectedKey, setSelectedKey] = useState<WritableKey>(WRITABLE_KEYS[0]);
  const [value, setValue] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);

  function submitUpdate(event: FormEvent) {
    event.preventDefault();
    const trimmed = value.trim();
    if (trimmed === "") {
      return;
    }
    const result = validateConfigValue(selectedKey, trimmed);
    if (!result.ok) {
      setValidationError(result.message);
      return;
    }
    setValidationError(null);
    update.mutate({
      key: selectedKey,
      value: result.value,
    });
  }

  return (
    <section className="panel data-panel" data-testid="config-panel">
      <header className="panel-header">
        <h3>配置</h3>
      </header>
      <div className="panel-body">
        {config.isPending ? <SkeletonRows count={4} /> : null}
        {config.isError ? (
          <ErrorState
            source="/config"
            message={config.error.message}
            onRetry={() => void config.refetch()}
          />
        ) : null}
        {config.isSuccess ? (
          <>
            <p className="panel-hint">
              白名单可写键：{WRITABLE_KEYS.join(" / ")}
            </p>
            <form className="config-form" onSubmit={submitUpdate}>
              <label className="form-field">
                <span className="form-label">键</span>
                <select
                  value={selectedKey}
                  onChange={(event) => {
                    setSelectedKey(event.target.value as WritableKey);
                    setValue("");
                    setValidationError(null);
                  }}
                >
                  {WRITABLE_KEYS.map((key) => (
                    <option key={key} value={key}>
                      {WRITABLE_KEY_LABELS[key]}
                    </option>
                  ))}
                </select>
              </label>
              <label className="form-field">
                <span className="form-label">值</span>
                {BOOL_KEYS.has(selectedKey) ? (
                  <select
                    value={value}
                    onChange={(event) => {
                      setValue(event.target.value);
                      setValidationError(null);
                    }}
                  >
                    <option value="">请选择</option>
                    <option value="true">true</option>
                    <option value="false">false</option>
                  </select>
                ) : (
                  <input
                    value={value}
                    onChange={(event) => {
                      setValue(event.target.value);
                      setValidationError(null);
                    }}
                    placeholder="数值"
                  />
                )}
              </label>
              <button
                type="submit"
                className="primary-button"
                disabled={value.trim() === "" || update.isPending}
              >
                {update.isPending ? "保存中…" : "保存"}
              </button>
            </form>
            {validationError !== null ? (
              <p
                className="inline-error"
                role="alert"
                data-testid="config-validation-error"
              >
                {validationError}
              </p>
            ) : null}
            {update.isError ? (
              <p className="inline-error" role="alert">
                保存失败：{update.error.message}
              </p>
            ) : null}
            {update.isSuccess && update.data.message ? (
              <p
                className="config-success"
                role="status"
                data-testid="config-updated"
              >
                {update.data.message}
              </p>
            ) : null}
            <pre className="plain-output" data-testid="config-snapshot">
              {JSON.stringify(config.data, null, 2)}
            </pre>
          </>
        ) : null}
      </div>
    </section>
  );
}

export default function DataPage() {
  const { workspaceId } = useParams();
  useWorkspaceSelection(workspaceId);
  const workspaceIdValue = workspaceId ?? "";

  return (
    <section
      className="data-page"
      data-testid="data-page"
      data-workspace={workspaceId}
    >
      <header className="page-header">
        <h2>数据</h2>
        <Link className="text-link" to={`/works/${workspaceIdValue}`}>
          返回作品
        </Link>
      </header>
      <div className="data-layout">
        <ExportPanel workspaceId={workspaceIdValue} />
        <ImportPanel />
      </div>
      <ConfigPanel />
    </section>
  );
}
