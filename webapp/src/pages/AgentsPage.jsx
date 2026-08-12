import { useEffect, useRef, useState } from "react";
import { ImageSquare, PencilSimple, TrashSimple } from "@phosphor-icons/react";
import { toast } from "sonner";
import { getAgents, getDiaries, postAgents } from "../api.js";
import { AgentAvatar } from "../components/features/agent-avatar.jsx";
import { EmptyState, ErrorState, LoadingState } from "../components/features/states.jsx";
import { PageHeader } from "../components/layout/page-header.jsx";
import { Badge } from "../components/ui/badge.jsx";
import { Button } from "../components/ui/button.jsx";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "../components/ui/dialog.jsx";
import { Input } from "../components/ui/input.jsx";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select.jsx";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs.jsx";
import {
  AVATAR_COLORS,
  avatarColorOf,
  compressAvatarImage,
  displayNameOf,
  exportCustomAgents,
  getCustomAgent,
  importCustomAgents,
  saveCustomAgent,
} from "../lib/agent-custom.js";
import { cn } from "../lib/utils.js";
import { useApi } from "../lib/use-api.js";

const modelOptions = ["deepseek-v4-pro", "deepseek-v4-flash"];

/** Agent 管理：人格档案与模型参数。@stable */
export default function AgentsPage() {
  const { data, error, loading, refresh } = useApi(getAgents, { interval: 30000 });
  const agents = data?.agents || [];
  const [selectedFile, setSelectedFile] = useState(null);
  const [draft, setDraft] = useState(null);
  const [diaries, setDiaries] = useState([]);
  const [busy, setBusy] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [editDraft, setEditDraft] = useState(null);
  const [customTick, setCustomTick] = useState(0);
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

  const openEdit = () => {
    if (!selected) return;
    const custom = selected ? getCustomDraft(selected) : null;
    setEditDraft(custom);
    setEditOpen(true);
  };

  const saveCustom = () => {
    if (!selected || !editDraft) return;
    saveCustomAgent(selected.file, editDraft);
    setEditOpen(false);
    setCustomTick((t) => t + 1);
    toast.success("自定义资料已保存");
  };

  const uploadAvatar = async (file) => {
    if (!file || !editDraft) return;
    try {
      const dataUrl = await compressAvatarImage(file, editDraft.avatarColor);
      setEditDraft((d) => ({ ...d, avatarImage: dataUrl }));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "头像处理失败");
    }
  };

  const exportCustom = () => {
    const blob = new Blob([exportCustomAgents()], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "agent-custom.json";
    a.click();
    URL.revokeObjectURL(url);
    toast.success("自定义资料已导出");
  };

  const importCustom = async (file) => {
    if (!file) return;
    let text;
    try {
      text = await file.text();
    } catch {
      toast.error("文件读取失败");
      return;
    }
    const result = importCustomAgents(text);
    if (result.ok) {
      setCustomTick((t) => t + 1);
      toast.success(`已导入 ${result.count} 条${result.skipped ? `，跳过 ${result.skipped} 条非法条目` : ""}`);
    } else {
      toast.error(`导入失败：${result.error}`);
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
            <Button variant="outline" size="sm" onClick={exportCustom}>
              导出资料
            </Button>
            <label className="cursor-pointer">
              <span className="inline-flex h-8 items-center justify-center rounded-control border border-line bg-surface px-3 text-xs text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink">
                导入资料
              </span>
              <input
                type="file"
                accept=".json,application/json"
                className="hidden"
                onChange={(e) => {
                  importCustom(e.target.files?.[0]);
                  e.target.value = "";
                }}
              />
            </label>
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
                  <AgentAvatar file={a.file} name={a.name} index={agents.indexOf(a)} />
                  <span className="min-w-0 flex-1 truncate">{displayNameOf(a, agents.indexOf(a))}</span>
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
                <AgentAvatar file={selected.file} name={selected.name} index={agents.indexOf(selected)} size="lg" />
                <div className="min-w-0">
                  <div className="text-base font-bold text-ink">{displayNameOf(selected, agents.indexOf(selected))}</div>
                  <div className="truncate text-xs text-ink-2">
                    {selected.file} · 节点：{(selected.nodes || []).join("、") || "未映射"}
                  </div>
                </div>
                <div className="ml-auto flex items-center gap-2">
                  <Badge tone="accent">{draft?.model}</Badge>
                  <Button variant="outline" size="sm" onClick={openEdit}>
                    <PencilSimple className="size-3.5" />
                    编辑资料
                  </Button>
                </div>
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

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="text-sm font-bold text-ink">自定义资料</DialogTitle>
          </DialogHeader>
          {editDraft ? (
            <div className="flex flex-col gap-4">
              <div className="flex items-center gap-3">
                <span
                  className="grid size-12 place-items-center overflow-hidden rounded-lg text-lg font-bold text-white"
                  style={{ background: editDraft.avatarColor }}
                >
                  {editDraft.avatarImage ? (
                    <img src={editDraft.avatarImage} alt="" className="size-full object-cover" />
                  ) : (
                    editDraft.avatarText.slice(0, 1) || "编"
                  )}
                </span>
                <div className="text-xs text-ink-3">预览：仅本机面板生效，不影响后端人格与发布。</div>
              </div>
              <div>
                <label className="mb-1.5 block text-xs text-ink-2">显示名</label>
                <Input
                  value={editDraft.displayName}
                  onChange={(e) => setEditDraft((d) => ({ ...d, displayName: e.target.value }))}
                  placeholder="如：掌印"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs text-ink-2">头像文字（取第一个字）</label>
                <Input
                  maxLength={1}
                  value={editDraft.avatarText}
                  onChange={(e) => setEditDraft((d) => ({ ...d, avatarText: e.target.value }))}
                  placeholder="掌"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs text-ink-2">头像颜色</label>
                <div className="flex gap-2">
                  {AVATAR_COLORS.map((color) => (
                    <button
                      key={color}
                      type="button"
                      aria-label={`颜色 ${color}`}
                      onClick={() => setEditDraft((d) => ({ ...d, avatarColor: color }))}
                      className={cn(
                        "size-7 rounded-full border-2 transition-transform",
                        editDraft.avatarColor === color
                          ? "scale-110 border-ink"
                          : "border-transparent hover:scale-105",
                      )}
                      style={{ background: color }}
                    />
                  ))}
                </div>
              </div>
              <div>
                <label className="mb-1.5 block text-xs text-ink-2">头像图片</label>
                <div className="flex gap-2">
                  <label className="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-control border border-line bg-surface px-3 text-xs text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink">
                    <ImageSquare className="size-3.5" />
                    上传图片
                    <input
                      type="file"
                      accept="image/*"
                      className="hidden"
                      onChange={(e) => {
                        uploadAvatar(e.target.files?.[0]);
                        e.target.value = "";
                      }}
                    />
                  </label>
                  {editDraft.avatarImage ? (
                    <button
                      type="button"
                      onClick={() => setEditDraft((d) => ({ ...d, avatarImage: "" }))}
                      className="inline-flex h-8 items-center gap-1.5 rounded-control border border-line bg-surface px-3 text-xs text-bad transition-colors hover:bg-bad-soft"
                    >
                      <TrashSimple className="size-3.5" />
                      移除
                    </button>
                  ) : null}
                  <span className="self-center text-[11px] text-ink-3">自动压缩为 96×96，随导出导入一起备份</span>
                </div>
              </div>
            </div>
          ) : null}
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditOpen(false)}>
              取消
            </Button>
            <Button onClick={saveCustom}>保存</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function getCustomDraft(agent) {
  const custom = getCustomAgent(agent.file);
  return {
    displayName: custom?.displayName || displayNameOf(agent),
    avatarText: custom?.avatarText || displayNameOf(agent).slice(0, 1),
    avatarColor: custom?.avatarColor || avatarColorOf(agent.file),
    avatarImage: custom?.avatarImage || "",
  };
}
