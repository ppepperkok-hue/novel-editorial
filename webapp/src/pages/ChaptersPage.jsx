import { useEffect, useState } from "react";
import { getChapterContent, getDashboard } from "../api.js";
import { EmptyState, ErrorState, LoadingState } from "../components/features/states.jsx";
import { PageHeader } from "../components/layout/page-header.jsx";
import { Badge } from "../components/ui/badge.jsx";
import { Button } from "../components/ui/button.jsx";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../components/ui/dialog.jsx";
import { Input } from "../components/ui/input.jsx";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table.jsx";
import { cn } from "../lib/utils.js";
import { useApi } from "../lib/use-api.js";

const STATUS_META = {
  draft: ["草稿", "neutral"],
  reviewed: ["待发布", "warn"],
  queued: ["待发布", "warn"],
  published: ["已发布", "ok"],
  failed: ["失败", "bad"],
};

/** 章节管理：状态筛选 + 表格 + 正文预览。@stable */
export default function ChaptersPage() {
  const { data, error, loading, refresh } = useApi(getDashboard, { interval: 30000 });
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [preview, setPreview] = useState(null);
  const [content, setContent] = useState("");

  const chapters = (data?.chapters || []).filter((c) => {
    if (filter !== "all" && c.status !== filter) return false;
    if (query) {
      const hay = `${c.title || ""} ${c.seq || ""}`.toLowerCase();
      if (!hay.includes(query.toLowerCase())) return false;
    }
    return true;
  });

  useEffect(() => {
    if (!preview) return;
    setContent("加载中…");
    getChapterContent(preview.id)
      .then((r) => setContent(r.content || "（无正文）"))
      .catch(() => setContent("正文加载失败"));
  }, [preview]);

  const filters = [
    ["all", "全部"],
    ["draft", "草稿"],
    ["reviewed", "待发布"],
    ["published", "已发布"],
  ];

  const novelTitle = (novelId) =>
    (data?.novels || []).find((n) => String(n.id) === String(novelId))?.title || `书 ${novelId}`;

  return (
    <>
      <PageHeader title="章节管理" desc="全部章节的写作状态、质量分与发布进度" />
      <div className="flex flex-wrap items-center gap-3 border-t border-line py-3">
        <div className="inline-flex overflow-hidden rounded-control border border-line">
          {filters.map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setFilter(id)}
              className={cn(
                "h-8 border-r border-line px-3.5 text-xs transition-colors last:border-r-0",
                filter === id ? "bg-ink font-semibold text-canvas" : "text-ink-2 hover:text-ink",
              )}
            >
              {label}
            </button>
          ))}
        </div>
        <Input
          className="h-8 max-w-[240px] text-xs"
          placeholder="搜索章节"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <span className="ml-auto text-xs text-ink-3">
          共 {chapters.length} 章 · 总字数 {chapters.reduce((a, c) => a + Number(c.words || 0), 0).toLocaleString()}
        </span>
      </div>

      {error ? (
        <ErrorState message="章节数据加载失败" detail={error} onRetry={refresh} />
      ) : loading ? (
        <LoadingState rows={6} />
      ) : chapters.length ? (
        <div className="rounded-card border border-line bg-surface px-4 py-1">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>章节</TableHead>
                <TableHead>作品</TableHead>
                <TableHead>标题</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>字数</TableHead>
                <TableHead>质量</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {chapters.slice(0, 200).map((c) => {
                const meta = STATUS_META[c.status] || [c.status, "neutral"];
                return (
                  <TableRow key={c.id}>
                    <TableCell className="font-mono text-xs text-ink-3">#{c.seq || c.id}</TableCell>
                    <TableCell className="text-xs text-ink-2">{novelTitle(c.novel_id)}</TableCell>
                    <TableCell className="text-[13px] font-medium text-ink">{c.title || "（无标题）"}</TableCell>
                    <TableCell>
                      <Badge tone={meta[1]}>{meta[0]}</Badge>
                    </TableCell>
                    <TableCell className="tabular-nums text-xs text-ink-2">{c.words || 0}</TableCell>
                    <TableCell className="tabular-nums text-xs text-ink-2">
                      {c.score != null ? Number(c.score).toFixed(0) : "—"}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button variant="ghost" size="sm" onClick={() => setPreview(c)}>
                        查看
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      ) : (
        <EmptyState title="没有符合条件的章节" hint="调整筛选条件，或等开工后产生新章节。" />
      )}

      <Dialog open={Boolean(preview)} onOpenChange={(v) => !v && setPreview(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="text-sm font-bold text-ink">
              第 {preview?.seq || preview?.id} 章 · {preview?.title || "无标题"}
            </DialogTitle>
          </DialogHeader>
          <pre className="max-h-[60vh] overflow-y-auto whitespace-pre-wrap rounded-control border border-line bg-surface-2 p-3 font-ui text-[13px] leading-relaxed text-ink-2">
            {content}
          </pre>
        </DialogContent>
      </Dialog>
    </>
  );
}
