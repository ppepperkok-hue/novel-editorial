import { Component, useEffect } from "react";

export function fmtTime(t, withDate = true) {
  if (!t) return "—";
  const s = String(t).replace("T", " ").slice(0, 19);
  return withDate ? s : s.slice(11);
}

export function fmtRelative(t) {
  if (!t) return "—";
  const ts = new Date(t).getTime();
  if (Number.isNaN(ts)) return "—";
  const diff = Date.now() - ts;
  if (diff < 60_000) return "刚刚";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`;
  return fmtTime(t);
}

export function fmtNum(n) {
  if (n === null || n === undefined || n === "") return "—";
  return Number(n).toLocaleString("zh-CN");
}

export function fmtMoney(n) {
  if (n === null || n === undefined) return "—";
  const v = Number(n);
  return v >= 0.01 ? "¥" + v.toFixed(2) : "¥" + v.toFixed(4);
}

export function ConfirmDialog({ open, title, body, confirmText = "确认", tone = "danger", busy = false, onCancel, onConfirm }) {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") onCancel?.();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onCancel]);

  if (!open) return null;
  return (
    <div className="modal-mask" onMouseDown={(e) => e.target === e.currentTarget && onCancel?.()}>
      <div className="modal confirm-modal">
        <div className="modal-head">
          <div className="flex items-center gap-2.5">
            <span className="confirm-icon">!</span>
            <span className="text-sm font-bold">{title}</span>
          </div>
          <button className="btn !px-2 !py-0.5 text-sm" onClick={onCancel}>✕</button>
        </div>
        <div className="modal-body">
          <div className="text-sm leading-relaxed text-slate-300">{body}</div>
          <div className="mt-5 flex justify-end gap-2">
            <button className="btn" onClick={onCancel} disabled={busy}>取消</button>
            <button
              className={`btn ${tone === "danger" ? "btn-danger" : tone === "ok" ? "btn-ok" : "btn-primary"}`}
              onClick={onConfirm}
              disabled={busy}
            >
              {busy ? "处理中…" : confirmText}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div className="panel p-6">
          <div className="mb-2 text-sm font-bold text-red-400">页面渲染出错</div>
          <pre className="code max-h-48 overflow-auto rounded-lg bg-[#1e1e1e] p-3 text-xs text-slate-400">
            {String(this.state.error?.stack || this.state.error)}
          </pre>
          <button className="btn mt-3" onClick={() => this.setState({ error: null })}>
            重试
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
