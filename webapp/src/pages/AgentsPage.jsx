import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { getAgents, getDiaries, postAgents } from "../api.js";
import { EmptyState, ErrorState, LoadingState } from "../components/features/states.jsx";
import { PageHeader } from "../components/layout/page-header.jsx";
import { Badge } from "../components/ui/badge.jsx";
import { Button } from "../components/ui/button.jsx";
import { Input } from "../components/ui/input.jsx";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select.jsx";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs.jsx";
import { cn } from "../lib/utils.js";
import { useApi } from "../lib/use-api.js";

const AGENT_NAMES = {
  planner: "文策",
  guard: "守界",
  writer: "墨白",
  editor: "润物",
  reviewer: "守正",
  reader: "阿读",
  memory: "录事",
  work_meta: "书案",
  eic: "掌印",
  ending_judge: "终局",
  knowledge_keeper: "博闻",
};

const modelOptions = ["deepseek-v4-pro", "deepseek-v4-flash"];

/** Agent 管理：人格档案与模型参数。@stable */
export default function AgentsPage() {
  const { data, error, loading, refresh } = useApi(getAgents, { interval: 30000 });
  const agents = data?.agents || [];
  const [selectedFile, setSelectedFile] = useState(null);
  const [draft, setDraft] = useState(null);
  const [diaries, setDiaries] = useState([]);
  const [busy, setBusy] = useState(false);
  const agentsRef = useRef([]);
  agentsRef.current = agents;

  const selected = agents.find((a) => a.file === selectedFile) || agents[0] || null;

  // 首次加载：默认选中第一位编辑（不随轮询覆盖用户选择）。
  useEffect(() => {
    if (!selectedFile && agentsRef.current.length > 0) {
      setSelectedFile(agentsRef.current[0].file);
    }
  }, [selectedFile, agents]);

  useEffect(() => {
    const a = agentsRef.current.find((x) => x.file === selectedFile) || agentsRef.current[0] || null;
    if (!a) return;
    setSelectedFile(a.file);
    setDraft({
      file: a.file,
      name: a.name,
      model: a.model || "deepseek-v4-flash",
      temperature: a.temperature ?? 0.7,
      prompt: a.prompt || a.description || "",
    });
    getDiaries(a.file.replace(/\.md$/, ""))
      .then((r) => setDiaries(r.diaries || []))
      .catch(() => setDiaries([]));
  }, [selectedFile]);

  const save = async () => {
    if (!draft) return;
    setBusy(true);
    try {
      const r = await postAgents({
        action: "save",
        file: draft.file,
        model: draft.model,
        temperature: Number(draft.temperature),
        prompt: draft.prompt,
      });
      if (r.ok) {
        toast.success(r.validation ? `${draft.name} 已保存并通过校验` : "已保存，但工作流校验未通过");
        refresh();
      } else {
        toast.error(`保存失败：${r.error || "未知"}`);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Agent 管理"
        desc="人格档案、模型参数与写作模式"
        actions={
          <>
            <Badge tone="ok">{agents.length} 位编辑</Badge>
            <Button size="sm" disabled={busy || !draft} onClick={save}>
              {busy ? "保存中…" : "保存并部署"}
            </Button>
          </>
        }
      />
      <div className="grid grid-cols-1 gap-7 lg:grid-cols-[minmax(0,1fr)_minmax(0,2.2fr)]">
        <aside className="min-w-0">
          <h2 className="mb-2.5 text-xs font-semibold text-ink">编辑名录</h2>
          {error ? (
            <ErrorState message="Agent 数据加载失败" detail={error} onRetry={refresh} />
          ) : loading ? (
            <LoadingState rows={8} />
          ) : agents.length ? (
            <div className="border-t border-line">
              {agents.map((a) => (
                <button
                  key={a.file}
                  type="button"
                  onClick={() => setSelectedFile(a.file)}
                  className={cn(
                    "flex w-full items-center gap-2.5 border-b border-line py-2.5 text-left text-[13px] transition-colors",
                    selected?.file === a.file
                      ? "font-semibold text-accent-ink"
                      : "text-ink-2 hover:text-ink",
                  )}
                >
                  <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-accent-soft text-xs font-semibold text-accent-ink">
                    {(AGENT_NAMES[a.file.replace(/\.md$/, "")] || a.name || a.file).slice(0, 1)}
                  </span>
                  <span className="min-w-0 flex-1 truncate">{a.name || a.file}</span>
                  <span className={cn("size-1.5 shrink-0 rounded-full", a.synced ? "bg-ok" : "bg-warn")} />
                </button>
              ))}
            </div>
          ) : (
            <EmptyState title="没有 Agent" />
          )}
        </aside>

        <section className="min-w-0 rounded-card border border-line bg-surface p-5">
          {!selected ? (
            <EmptyState title="请选择一位编辑" />
          ) : (
            <>
              <div className="flex items-center gap-3">
                <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-accent-soft text-base font-semibold text-accent-ink">
                  {(AGENT_NAMES[selected.file.replace(/\.md$/, "")] || selected.name || "?").slice(0, 1)}
                </span>
                <div className="min-w-0">
                  <div className="text-base font-bold text-ink">{selected.name || selected.file}</div>
                  <div className="truncate text-xs text-ink-2">
                    {selected.file} · 节点：{(selected.nodes || []).join("、") || "未映射"}
                  </div>
                </div>
                <Badge tone="accent" className="ml-auto">
                  {draft?.model}
                </Badge>
              </div>

              <Tabs defaultValue="persona" className="mt-4">
                <TabsList>
                  <TabsTrigger value="persona">人格档案</TabsTrigger>
                  <TabsTrigger value="diary">日记</TabsTrigger>
                  <TabsTrigger value="weekly">周记</TabsTrigger>
                  <TabsTrigger value="meeting">会议</TabsTrigger>
                </TabsList>
                <TabsContent value="persona">
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <div>
                      <label className="mb-1.5 block text-xs text-ink-2">模型</label>
                      <Select
                        value={draft?.model}
                        onValueChange={(v) => setDraft((d) => (d ? { ...d, model: v } : d))}
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="选择模型" />
                        </SelectTrigger>
                        <SelectContent>
                          {modelOptions.map((m) => (
                            <SelectItem key={m} value={m}>
                              {m}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <label className="mb-1.5 block text-xs text-ink-2">温度</label>
                      <Input
                        type="number"
                        step="0.1"
                        min="0"
                        max="2"
                        value={draft?.temperature}
                        onChange={(e) =>
                          setDraft((d) => (d ? { ...d, temperature: Number(e.target.value) } : d))
                        }
                      />
                    </div>
                  </div>
                  <div className="mt-4">
                    <label className="mb-1.5 block text-xs text-ink-2">人格档案正文</label>
                    <textarea
                      className="min-h-[220px] w-full resize-y rounded-control border border-line bg-surface p-2.5 text-[13px] leading-relaxed text-ink outline-none transition-colors focus:border-accent"
                      value={draft?.prompt || ""}
                      onChange={(e) => setDraft((d) => (d ? { ...d, prompt: e.target.value } : d))}
                    />
                  </div>
                </TabsContent>
                <TabsContent value="diary">
                  {diaries.length ? (
                    <div className="border-t border-line">
                      {diaries.slice(0, 10).map((d) => (
                        <div key={d.id} className="border-b border-line py-3 text-xs last:border-b-0">
                          <div className="font-mono text-[11px] text-ink-3">
                            {d.diary_type || "daily"} · {d.created_at}
                          </div>
                          <p className="mt-1 whitespace-pre-wrap leading-relaxed text-ink-2">
                            {typeof d.content === "string" ? d.content.slice(0, 300) : JSON.stringify(d.content)}
                          </p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyState title="还没有日记" hint="日更结束后，每位编辑会写下当日日记。" />
                  )}
                </TabsContent>
                <TabsContent value="weekly">
                  <EmptyState title="周记视图" hint="周会前生成的每周记忆将在这里展示。" />
                </TabsContent>
                <TabsContent value="meeting">
                  <EmptyState title="会议视图" hint="该编辑的会议发言与纪要将在后续版本展示。" />
                </TabsContent>
              </Tabs>
            </>
          )}
        </section>
      </div>
    </>
  );
}
