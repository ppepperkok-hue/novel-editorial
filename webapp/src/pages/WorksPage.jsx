import { useState } from "react";
import { getDashboard, getNovelKnowledge } from "../api.js";
import { EmptyState, ErrorState, LoadingState } from "../components/features/states.jsx";
import { PageHeader } from "../components/layout/page-header.jsx";
import { Badge } from "../components/ui/badge.jsx";
import { Button } from "../components/ui/button.jsx";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs.jsx";
import { cn } from "../lib/utils.js";
import { useApi } from "../lib/use-api.js";

const STATUS_LABEL = {
  publishing: "连载中",
  finishing: "收尾中",
  finished: "已完结",
  planning: "规划中",
  ready: "待绑定",
};

const STATUS_TONE = {
  publishing: "ok",
  finishing: "warn",
  finished: "ok",
  planning: "warn",
  ready: "accent",
};

/** 作品库：项目列表 + 设定详情。@stable */
export default function WorksPage() {
  const { data, error, loading, refresh } = useApi(getDashboard, { interval: 30000 });
  const novels = data?.novels || [];
  const [selectedId, setSelectedId] = useState(null);
  const [knowledge, setKnowledge] = useState(null);
  const selected = novels.find((n) => n.id === selectedId) || novels[0] || null;

  const loadKnowledge = (novelId) => {
    setKnowledge(null);
    getNovelKnowledge(novelId)
      .then((r) => setKnowledge(r.items || r.knowledge || []))
      .catch(() => setKnowledge([]));
  };

  const pick = (novel) => {
    setSelectedId(novel.id);
    loadKnowledge(novel.id);
  };

  return (
    <>
      <PageHeader
        title="作品库"
        desc="每个项目的完整设定：大纲、角色与世界规则"
        actions={<Button size="sm">新建项目</Button>}
      />
      <div className="grid grid-cols-1 gap-7 lg:grid-cols-[minmax(0,1fr)_minmax(0,2.2fr)]">
        <aside className="min-w-0">
          <h2 className="mb-2.5 text-xs font-semibold text-ink">项目</h2>
          {error ? (
            <ErrorState message="作品数据加载失败" detail={error} onRetry={refresh} />
          ) : loading ? (
            <LoadingState rows={4} />
          ) : novels.length ? (
            <div className="border-t border-line">
              {novels.map((n) => (
                <button
                  key={n.id}
                  type="button"
                  onClick={() => pick(n)}
                  className={cn(
                    "flex w-full items-center gap-3 border-b border-line py-2.5 text-left transition-colors",
                    selected?.id === n.id ? "text-accent-ink" : "text-ink hover:text-ink-2",
                  )}
                >
                  <span
                    className={cn(
                      "size-[34px] shrink-0 rounded-[4px] border border-line",
                      selected?.id === n.id ? "bg-accent-soft" : "bg-surface-2",
                    )}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-semibold">{n.title}</span>
                    <span className="block truncate text-[11.5px] text-ink-3">
                      {n.chapters ?? 0} 章 · 已发布 {n.published ?? 0}
                    </span>
                  </span>
                  <Badge tone={STATUS_TONE[n.status] || "neutral"}>{STATUS_LABEL[n.status] || n.status}</Badge>
                </button>
              ))}
            </div>
          ) : (
            <EmptyState title="还没有项目" hint="新建项目后，大纲与角色设定会出现在这里。" />
          )}
        </aside>

        <section className="min-w-0 rounded-card border border-line bg-surface p-5">
          {!selected ? (
            <EmptyState title="请选择项目" />
          ) : (
            <>
              <div className="flex items-baseline justify-between">
                <div className="text-base font-bold text-ink">{selected.title}</div>
                <Badge tone={STATUS_TONE[selected.status] || "neutral"}>
                  {STATUS_LABEL[selected.status] || selected.status}
                </Badge>
              </div>
              <Tabs defaultValue="outline" className="mt-4">
                <TabsList>
                  <TabsTrigger value="outline">大纲</TabsTrigger>
                  <TabsTrigger value="protagonist">主角</TabsTrigger>
                  <TabsTrigger value="characters">角色卡</TabsTrigger>
                  <TabsTrigger value="world">世界规则</TabsTrigger>
                  <TabsTrigger value="knowledge">知识库</TabsTrigger>
                </TabsList>

                <TabsContent value="outline">
                  {selected.volume_goal ? (
                    <p className="mb-3 text-xs leading-relaxed text-ink-2">
                      卷目标：{selected.volume_goal}
                    </p>
                  ) : null}
                  {Object.keys(selected.outline || {}).length ? (
                    <div className="border-t border-line">
                      {Object.entries(selected.outline).map(([key, value]) => (
                        <div key={key} className="border-b border-line py-2.5 text-xs last:border-b-0">
                          <span className="font-mono text-[11px] text-ink-3">{key}</span>
                          <p className="mt-1 whitespace-pre-wrap leading-relaxed text-ink-2">
                            {typeof value === "string" ? value : JSON.stringify(value)}
                          </p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyState title="还没有大纲" hint={selected.premise || "在规划阶段生成。"} />
                  )}
                </TabsContent>

                <TabsContent value="protagonist">
                  {(selected.protagonists || []).length ? (
                    <div className="border-t border-line">
                      {selected.protagonists.map((p, i) => (
                        <div key={i} className="border-b border-line py-2.5 text-xs last:border-b-0">
                          <span className="font-semibold text-ink">{typeof p === "string" ? p : p.name || `主角 ${i + 1}`}</span>
                          {typeof p === "object" && p.desc ? (
                            <p className="mt-1 leading-relaxed text-ink-2">{p.desc}</p>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyState title="还没有主角设定" />
                  )}
                </TabsContent>

                <TabsContent value="characters">
                  {(selected.characters || []).length ? (
                    <div className="border-t border-line">
                      {selected.characters.map((c, i) => (
                        <div key={i} className="border-b border-line py-2.5 text-xs last:border-b-0">
                          <div className="font-semibold text-ink">
                            {c.name} <span className="font-normal text-ink-3">· {c.role}</span>
                          </div>
                          {c.traits ? <p className="mt-1 leading-relaxed text-ink-2">特质：{c.traits}</p> : null}
                          {c.goals ? <p className="mt-0.5 leading-relaxed text-ink-2">目标：{c.goals}</p> : null}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyState title="还没有角色卡" />
                  )}
                </TabsContent>

                <TabsContent value="world">
                  <div className="border-t border-line">
                    <div className="border-b border-line py-2.5 text-xs last:border-b-0">
                      <div className="text-[11px] uppercase tracking-[0.05em] text-ink-3">简介</div>
                      <p className="mt-1 leading-relaxed text-ink-2">{selected.abstract || "—"}</p>
                    </div>
                    <div className="border-b border-line py-2.5 text-xs last:border-b-0">
                      <div className="text-[11px] uppercase tracking-[0.05em] text-ink-3">卖点</div>
                      <p className="mt-1 leading-relaxed text-ink-2">{selected.selling_point || "—"}</p>
                    </div>
                    <div className="border-b border-line py-2.5 text-xs last:border-b-0">
                      <div className="text-[11px] uppercase tracking-[0.05em] text-ink-3">题材</div>
                      <p className="mt-1 leading-relaxed text-ink-2">
                        {selected.genre || "—"} · {(selected.tags || []).join("、") || "无标签"}
                      </p>
                    </div>
                  </div>
                </TabsContent>

                <TabsContent value="knowledge">
                  {knowledge === null ? (
                    <LoadingState rows={3} />
                  ) : knowledge.length ? (
                    <div className="border-t border-line">
                      {knowledge.slice(0, 12).map((k, i) => (
                        <div key={i} className="border-b border-line py-2.5 text-xs last:border-b-0">
                          <span className="font-mono text-[11px] text-ink-3">{k.category || k.type || "知识"}</span>
                          <p className="mt-1 leading-relaxed text-ink-2">
                            {typeof k.content === "string" ? k.content.slice(0, 200) : JSON.stringify(k)}
                          </p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyState title="知识库为空" hint="随故事推进自动沉淀的设定与规则会保存在这里。" />
                  )}
                </TabsContent>
              </Tabs>
            </>
          )}
        </section>
      </div>
    </>
  );
}
