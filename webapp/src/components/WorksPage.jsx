import { useState } from "react";
import {
  bindBook,
  confirmNextBook,
  createBookOnFanqie,
  deleteBookOnFanqie,
  exportNovels,
  getCharacterEvolution,
  getEndingStatus,
  getNovelKnowledge,
  upsertNovelKnowledge,
} from "../api.js";
import { useEffect } from "react";

function Field({ label, children }) {
  return (
    <div className="rounded-lg border border-[var(--line)] bg-[var(--code-bg)] p-3">
      <div className="label !mb-2">{label}</div>
      <div className="text-sm leading-relaxed text-slate-300">{children || <span className="muted">暂无</span>}</div>
    </div>
  );
}

function CharacterCard({ c, evolutions }) {
  const mine = (evolutions || []).filter((e) => e.name === c.name).slice(0, 5);
  return (
    <div className="rounded-lg border border-[var(--line)] bg-[var(--code-bg)] p-2.5">
      <div className="flex items-baseline gap-2">
        <span className="text-sm font-semibold text-sky-400">{c.name}</span>
        <span className="muted text-xs">{c.role}</span>
      </div>
      <div className="muted mt-1 text-xs leading-relaxed">
        {c.personality || c.identity || "无性格描述"}
        {c.speech_style ? ` · 口吻：${c.speech_style}` : ""}
        {c.current_state ? ` · 当前：${c.current_state}` : ""}
      </div>
      {c.goals ? <div className="mt-1 text-xs text-amber-400/90">目标：{c.goals}</div> : null}
      {c.traits ? <div className="mt-0.5 text-xs text-slate-400">特质：{c.traits}</div> : null}
      {mine.length ? (
        <div className="mt-1.5 border-t border-[var(--line-soft)] pt-1.5">
          <div className="mb-1 text-[11px] text-[var(--accent-text)]">成长轨迹</div>
          {mine.map((e, i) => (
            <div key={i} className="text-[11px] leading-relaxed text-slate-500">
              · {e.chapter_id ? `第 ${e.chapter_id} 章` : "周会"}：{e.change_log}
              {e.arc ? <span className="text-amber-400/80"> [{e.arc}]</span> : null}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

const CATEGORY_LABELS = {
  character: "角色",
  world_rule: "世界观",
  item: "物品/金手指",
  faction: "势力",
  location: "地点",
  power: "力量体系",
  plot: "剧情事实",
  timeline: "时间线",
};

function NovelKnowledgeBlock({ novelId, pushToast }) {
  const [items, setItems] = useState([]);
  const [editor, setEditor] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = () => {
    getNovelKnowledge(novelId)
      .then((r) => setItems(r.items || []))
      .catch(() => setItems([]));
  };
  useEffect(() => {
    load();
  }, [novelId]);

  const save = async () => {
    if (!editor) return;
    setBusy(true);
    try {
      const r = await upsertNovelKnowledge({
        novel_id: novelId,
        category: editor.category,
        entity: editor.entity,
        content: editor.content,
        change_note: editor.change_note,
      });
      pushToast(r.ok ? "设定已保存" : "保存失败：" + (r.error || "未知"), r.ok ? "ok" : "bad");
      if (r.ok) {
        setEditor(null);
        load();
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <Field label={`设定知识库（${items.length}）`}>
      <div className="flex flex-col gap-1.5">
        {items.map((it) => (
          <div key={it.id} className="rounded-md bg-[var(--bg-soft)] px-2 py-1.5">
            <div className="flex items-center gap-2 text-xs">
              <span className="text-sky-400">{CATEGORY_LABELS[it.category] || it.category}</span>
              <span className="font-semibold text-slate-200">{it.entity}</span>
              <span className="muted">v{it.version}</span>
              {it.source_chapter ? <span className="muted">第 {it.source_chapter} 章</span> : null}
              <button
                className="btn ml-auto !px-2 !py-0.5 text-xs"
                onClick={() => setEditor({ id: it.id, category: it.category, entity: it.entity, content: it.content, change_note: "" })}
              >
                编辑
              </button>
            </div>
            <div className="muted mt-1 break-words text-xs leading-relaxed">{it.content}</div>
          </div>
        ))}
        {!items.length ? <div className="muted text-xs">还没有设定条目。日更会自动同步角色状态与剧情事实。</div> : null}

        {editor ? (
          <div className="mt-1 rounded-md border border-[var(--line)] p-2">
            <div className="grid grid-cols-2 gap-1.5">
              <label className="text-xs muted">
                分类
                <select className="input mt-0.5" value={editor.category} onChange={(e) => setEditor({ ...editor, category: e.target.value })}>
                  {Object.entries(CATEGORY_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </label>
              <label className="text-xs muted">
                实体名（角色/物品/地点）
                <input className="input mt-0.5" value={editor.entity} onChange={(e) => setEditor({ ...editor, entity: e.target.value })} />
              </label>
            </div>
            <label className="mt-1.5 block text-xs muted">
              设定内容
              <textarea className="input mt-0.5 h-20 w-full" value={editor.content} onChange={(e) => setEditor({ ...editor, content: e.target.value })} />
            </label>
            <div className="mt-1.5 flex justify-end gap-2">
              <button className="btn !px-2.5 !py-0.5 text-xs" onClick={() => setEditor(null)}>取消</button>
              <button className="btn btn-ok !px-2.5 !py-0.5 text-xs" disabled={busy} onClick={save}>保存</button>
            </div>
          </div>
        ) : (
          <button
            className="btn mt-1 !px-2.5 !py-0.5 text-xs"
            onClick={() => setEditor({ category: "character", entity: "", content: "", change_note: "手动录入" })}
          >
            + 新增设定
          </button>
        )}
      </div>
    </Field>
  );
}

export default function WorksPage({ data, pushToast }) {
  const [open, setOpen] = useState({});
  const [query, setQuery] = useState("");
  const [exporting, setExporting] = useState(false);
  const [ending, setEnding] = useState([]);
  const [binding, setBinding] = useState(null);
  const [creating, setCreating] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [bindBookId, setBindBookId] = useState("");
  const [bindVolumeId, setBindVolumeId] = useState("");
  const [showManualBind, setShowManualBind] = useState(false);
  const [copiedCover, setCopiedCover] = useState(false);
  const [evoMap, setEvoMap] = useState({});
  const novels = data?.novels || [];

  const loadEnding = () => {
    getEndingStatus()
      .then((r) => setEnding(r.novels || []))
      .catch((e) => pushToast("刷新结束状态失败：" + e, "bad"));
  };

  useEffect(() => {
    getEndingStatus()
      .then((r) => setEnding(r.novels || []))
      .catch(() => {});
  }, []);

  const toggle = (id) => setOpen((o) => ({ ...o, [id]: !o[id] }));
  const allOpen = novels.length > 0 && novels.every((n) => open[n.id]);
  const setAll = (v) => setOpen(Object.fromEntries(novels.map((n) => [n.id, v])));
  const doExport = async () => {
    setExporting(true);
    try {
      const r = await exportNovels();
      if (r.ok) {
        pushToast(`已存档 ${r.novels} 部 · ${r.chapters} 章 · ${r.words.toLocaleString()} 字 → ${r.path}`, "ok");
      } else {
        pushToast("导出失败：" + (r.error || "未知"), "bad");
      }
    } catch (e) {
      pushToast("导出请求失败：" + e, "bad");
    } finally {
      setExporting(false);
    }
  };

  const nextBook = ending.find((n) => n.status === "planning" || n.status === "ready");
  const finishing = ending.find((n) => n.status === "finishing");
  const finished = ending.find((n) => n.status === "finished");

  const toggleWithEvo = (id) => {
    const next = !open[id];
    toggle(id);
    if (next && !evoMap[id]) {
      getCharacterEvolution(id)
        .then((r) => setEvoMap((m) => ({ ...m, [id]: r.evolution || [] })))
        .catch(() => {});
    }
  };
  const filtered = query.trim()
    ? novels.filter((n) => {
        const hay = [n.title, n.genre, n.status, n.abstract, n.premise, (n.tags || []).join(" ")]
          .join(" ")
          .toLowerCase();
        return hay.includes(query.trim().toLowerCase());
      })
    : novels;

  if (!novels.length) {
    return <div className="panel"><div className="empty">暂无作品，等待流水线第一次运行后自动创建。</div></div>;
  }

  return (
    <div className="flex flex-col gap-4">
      {finishing || finished ? (
        <div className={`panel p-4 ${finished ? "" : "border-amber-900/50"}`}>
          <div className="flex flex-wrap items-center gap-2">
            {finishing ? (
              <>
                <span className="chip chip-warn">收尾中</span>
                <span className="text-sm">「{finishing.title}」还剩 {finishing.finish_remaining} 章收尾</span>
                {finishing.finish_note ? (
                  <span className="muted text-xs">
                    评估理由：{String(finishing.finish_note).slice(0, 120)}
                  </span>
                ) : null}
              </>
            ) : (
              <>
                <span className="chip chip-ok">已完结</span>
                <span className="text-sm">「{finished.title}」已完成</span>
                <span className="chip chip-warn">请到番茄后台标记完结</span>
              </>
            )}
          </div>
        </div>
      ) : null}

      {nextBook ? (
        <div className="panel p-4">
          <div className="mb-2 flex items-center gap-2">
            <span className="chip chip-info">新书创意</span>
            <span className="text-sm font-bold">{nextBook.title || "未命名"}</span>
            <span className="muted text-xs">{nextBook.status === "ready" ? "已确认，待绑定" : "待确认"}</span>
          </div>
          <div className="muted mb-2 text-xs">{nextBook.premise || nextBook.abstract}</div>
          <div className="mb-3 flex flex-wrap gap-1.5">
            {(() => {
              let tags = [];
              try {
                tags = JSON.parse(nextBook.tags || "[]") || [];
              } catch {
                tags = [];
              }
              return tags.map((t) => (
              <span key={t} className="chip">{t}</span>
              ));
            })()}
            {nextBook.selling_point ? <span className="chip chip-info">卖点：{nextBook.selling_point.slice(0, 40)}</span> : null}
          </div>
          {nextBook.cover_prompt ? (
            <div className="mb-3 rounded-lg border border-[var(--line)] bg-[var(--code-bg)] p-3">
              <div className="mb-1 flex items-center gap-2">
                <span className="label !mb-0">封面提示词（豆包出图用）</span>
                <button
                  className="btn !px-2 !py-0.5 text-xs"
                  onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(nextBook.cover_prompt);
                      setCopiedCover(true);
                      setTimeout(() => setCopiedCover(false), 2000);
                    } catch (e) {
                      pushToast("复制失败：" + e, "bad");
                    }
                  }}
                >
                  {copiedCover ? "已复制" : "复制"}
                </button>
              </div>
              <div className="whitespace-pre-wrap text-xs leading-relaxed text-slate-300">
                {nextBook.cover_prompt}
              </div>
            </div>
          ) : null}
          {nextBook.status === "planning" ? (
            <button
              className="btn btn-primary"
              onClick={async () => {
                const r = await confirmNextBook(nextBook.id);
                pushToast(r.ok ? r.note : "失败：" + (r.error || "未知"), r.ok ? "ok" : "bad");
                loadEnding();
              }}
            >
              确认创意，准备绑定番茄新书
            </button>
          ) : (
            <div className="flex flex-col gap-2">
              <div className="flex flex-wrap items-center gap-3">
                <button
                  className="btn btn-ok"
                  disabled={creating === nextBook.id}
                  onClick={async () => {
                    setCreating(nextBook.id);
                    try {
                      const r = await createBookOnFanqie(nextBook.id);
                      pushToast(
                        r.ok ? r.note : "自动建书失败：" + (r.error || "未知"),
                        r.ok ? "ok" : "bad"
                      );
                    } catch (e) {
                      pushToast("自动建书请求失败：" + e, "bad");
                    } finally {
                      setCreating(null);
                      loadEnding();
                    }
                  }}
                >
                  {creating === nextBook.id ? "正在番茄建书…" : "一键自动建书"}
                </button>
                <button
                  className="btn !px-2 !py-0.5 text-xs"
                  onClick={() => setShowManualBind((v) => !v)}
                >
                  {showManualBind ? "收起手动绑定" : "手动绑定（备用）"}
                </button>
              </div>
              {showManualBind ? (
                <div className="flex flex-wrap items-end gap-2">
                  <label className="text-xs muted">
                    番茄 book_id
                    <input className="input mt-1 !w-64" value={bindBookId} onChange={(e) => setBindBookId(e.target.value)} placeholder="在番茄后台建书后填写" />
                  </label>
                  <label className="text-xs muted">
                    volume_id（可选）
                    <input className="input mt-1 !w-40" value={bindVolumeId} onChange={(e) => setBindVolumeId(e.target.value)} />
                  </label>
                  <button
                    className="btn"
                    disabled={!bindBookId || binding === nextBook.id}
                    onClick={async () => {
                      setBinding(nextBook.id);
                      try {
                        const r = await bindBook(nextBook.id, bindBookId.trim(), bindVolumeId.trim());
                        pushToast(r.ok ? r.note : "绑定失败：" + (r.error || "未知"), r.ok ? "ok" : "bad");
                      } catch (e) {
                        pushToast("绑定请求失败：" + e, "bad");
                      } finally {
                        setBinding(null);
                        loadEnding();
                      }
                    }}
                  >
                    {binding === nextBook.id ? "绑定中…" : "绑定新书"}
                  </button>
                </div>
              ) : null}
              <div className="muted text-xs">
                自动建书会用书名/简介/分类/标签/主角名在番茄创建书籍并自动绑定；成功后日更将切换到新书。
              </div>
            </div>
          )}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <input
          className="input !w-64"
          placeholder="搜索书名 / 类型 / 标签 / 简介…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button className="btn ml-auto" onClick={() => setAll(!allOpen)}>
          {allOpen ? "全部收起" : "全部展开"}
        </button>
        <button className="btn btn-primary" disabled={exporting} onClick={doExport}>
          {exporting ? "存档中…" : "⬇ 导出存档"}
        </button>
        <span className="muted text-xs">共 {filtered.length} 部</span>
      </div>

      {filtered.map((n) => {
        const o = n.outline || {};
        const bible = o.bible || {};
        const chars = (n.characters || []).map((c) => (
          <CharacterCard key={c.name + c.role} c={c} evolutions={evoMap[n.id]} />
        ));
        const bibleChars = (bible.characters || []).map((c) => (
          <CharacterCard key={"b" + c.name + c.role} c={c} evolutions={evoMap[n.id]} />
        ));
        const rels = (bible.relationships || []).map((r, i) => (
          <div key={i} className="rounded-md bg-[var(--code-bg)] px-2.5 py-1.5 text-xs text-slate-400">
            {r.from} <span className="text-sky-400">— {r.relation || "关系"} —</span> {r.to}
            {r.note ? <span className="muted">：{r.note}</span> : ""}
          </div>
        ));
        const rules = (bible.world_rules || []).map((w, i) => (
          <div key={i} className="text-xs text-slate-400">· {w}</div>
        ));
        const chs = [o.chapter1, o.chapter2].filter(Boolean).map((c) => (
          <div key={c.title} className="rounded-lg border border-[var(--line)] bg-[var(--code-bg)] p-2.5">
            <div className="text-sm font-semibold text-amber-400">{c.title}</div>
            <div className="muted mt-0.5 text-xs leading-relaxed">{c.outline}</div>
            {c.hook ? <div className="mt-1 text-xs text-emerald-400">钩子：{c.hook}</div> : null}
            {c.conflict ? <div className="mt-0.5 text-xs text-red-400/90">冲突：{c.conflict}</div> : null}
          </div>
        ));
        const isOpen = open[n.id];
        return (
          <section key={n.id} className="panel overflow-hidden">
            <div className="flex cursor-pointer items-center justify-between gap-3 px-5 py-4" onClick={() => toggleWithEvo(n.id)}>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-base font-bold">{n.title}</h3>
                  <span className={`chip ${n.status === "publishing" ? "chip-ok" : n.status === "finishing" ? "chip-warn" : n.status === "finished" ? "chip-ok" : n.status === "planning" ? "chip-warn" : "chip-info"}`}>
                    {n.status === "publishing" ? "连载中" : n.status === "finishing" ? "收尾中" : n.status === "finished" ? "已完结" : n.status === "planning" ? "规划中" : n.status === "ready" ? "待绑定" : n.status}
                  </span>
                  <span className="chip">{n.platform} · {n.genre}</span>
                </div>
                <div className="muted mt-1 text-xs">
                  章节 {n.chapters} · 已发布 {n.published}
                  {n.last_chapter_title ? ` · 最新：${n.last_chapter_title}` : ""}
                  {n.updated_at ? ` · 更新 ${n.updated_at.slice(5, 16)}` : ""}
                </div>
              </div>
              <span className="muted shrink-0 text-lg">{isOpen ? "▾" : "▸"}</span>
            </div>

            {isOpen ? (
              <div className="flex flex-col gap-4 border-t border-[var(--line)] px-5 py-4">
                <div className="flex flex-wrap gap-1.5">
                  {(n.tags || []).map((t) => (
                    <span key={t} className="chip chip-info">{t}</span>
                  ))}
                  {!(n.tags || []).length ? <span className="chip">无标签</span> : null}
                </div>

                <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                  <Field label="作品简介">{n.abstract || n.premise}</Field>
                  <Field label="核心创意（卖点）">{n.premise || n.selling_point}</Field>
                  <Field label="卷目标 / 连载计划">{n.volume_goal || o.volume_goal}</Field>
                  <Field label="关键词">{Array.isArray(o.keywords) ? o.keywords.join("、") : o.keywords}</Field>
                </div>

                <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                  <Field label={`主角（${chars.length}）`}>
                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">{chars}</div>
                  </Field>
                  <Field label={`角色卡（${bibleChars.length}）`}>
                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">{bibleChars}</div>
                  </Field>
                </div>

                <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                  <Field label={`人物关系（${rels.length}）`}>
                    <div className="flex flex-col gap-1.5">{rels}</div>
                  </Field>
                  <Field label={`世界观规则（${rules.length}）`}>
                    <div className="flex flex-col gap-1">{rules}</div>
                  </Field>
                </div>

                

                {chs.length ? (
                  <Field label="本章细纲（两章）">
                    <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">{chs}</div>
                  </Field>
                ) : null}

                {o.blueprints?.some((b) => b.plant_foreshadow || b.recover_foreshadow) ? (
                  <Field label="伏笔台账（按蓝图聚合）">
                    <div className="flex flex-col gap-1 text-xs">
                      {o.blueprints.map((b) => {
                        const plants = b.plant_foreshadow || [];
                        const recovers = b.recover_foreshadow || [];
                        if (!plants.length && !recovers.length) return null;
                        const label = b.seq ? `第 ${b.seq} 章 ${b.title || ''}：` : (b.title || '');
                        return (
                          <div key={b.seq ?? b.title}>
                            <span className="text-sky-400">{label}</span>
                            {plants.length ? <span className="text-amber-400">埋：{typeof plants === "string" ? plants : plants.join("；")} </span> : null}
                            {recovers.length ? <span className="text-emerald-400">收：{typeof recovers === "string" ? recovers : recovers.join("；")}</span> : null}
                          </div>
                        );
                      })}
                    </div>
                  </Field>
                ) : null}

<NovelKnowledgeBlock novelId={n.id} pushToast={pushToast} />
                <div className="muted text-xs">书 ID：{n.book_id || "未关联"} · 番茄章节 ID 见章节管理</div>
                {n.book_id ? (
                  <div className="flex items-center gap-2 border-t border-[var(--line-soft)] pt-3">
                    <button
                      className="btn !border-red-900/60 !text-red-400"
                      disabled={deleting === n.id}
                      onClick={async () => {
                        if (!window.confirm(`确定删除番茄上的《${n.title}》？删除后不可恢复，本地作品数据会一并清空。`)) return;
                        setDeleting(n.id);
                        try {
                          const r = await deleteBookOnFanqie(n.id);
                          pushToast(r.ok ? r.note : "删除失败：" + (r.error || "未知"), r.ok ? "ok" : "bad");
                        } catch (e) {
                          pushToast("删除请求失败：" + e, "bad");
                        } finally {
                          setDeleting(null);
                          loadEnding();
                        }
                      }}
                    >
                      {deleting === n.id ? "删除中…" : "删除番茄书籍"}
                    </button>
                    <span className="muted text-xs">平台侧删除，本地作品一并清空</span>
                  </div>
                ) : null}
              </div>
            ) : null}
          </section>
        );
      })}
      {!filtered.length ? (
        <div className="panel"><div className="empty">没有匹配「{query}」的作品</div></div>
      ) : null}
    </div>
  );
}
