import { useState } from "react";

function Field({ label, children }) {
  return (
    <div className="rounded-lg border border-[#1a2332] bg-[#0a0f18] p-3">
      <div className="label !mb-2">{label}</div>
      <div className="text-sm leading-relaxed text-slate-300">{children || <span className="muted">暂无</span>}</div>
    </div>
  );
}

function CharacterCard({ c }) {
  return (
    <div className="rounded-lg border border-[#1a2332] bg-[#0a0f18] p-2.5">
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
    </div>
  );
}

export default function WorksPage({ data }) {
  const [open, setOpen] = useState({});
  const novels = data?.novels || [];

  const toggle = (id) => setOpen((o) => ({ ...o, [id]: !o[id] }));

  if (!novels.length) {
    return <div className="panel"><div className="empty">暂无作品，等待流水线第一次运行后自动创建。</div></div>;
  }

  return (
    <div className="flex flex-col gap-4">
      {novels.map((n) => {
        const o = n.outline || {};
        const bible = o.bible || {};
        const chars = (n.characters || []).map((c) => (
          <CharacterCard key={c.name + c.role} c={c} />
        ));
        const bibleChars = (bible.characters || []).map((c) => (
          <CharacterCard key={"b" + c.name + c.role} c={c} />
        ));
        const rels = (bible.relationships || []).map((r, i) => (
          <div key={i} className="rounded-md bg-[#0a0f18] px-2.5 py-1.5 text-xs text-slate-400">
            {r.from} <span className="text-sky-400">— {r.relation || "关系"} —</span> {r.to}
            {r.note ? <span className="muted">：{r.note}</span> : ""}
          </div>
        ));
        const rules = (bible.world_rules || []).map((w, i) => (
          <div key={i} className="text-xs text-slate-400">· {w}</div>
        ));
        const chs = [o.chapter1, o.chapter2].filter(Boolean).map((c) => (
          <div key={c.title} className="rounded-lg border border-[#1a2332] bg-[#0a0f18] p-2.5">
            <div className="text-sm font-semibold text-amber-400">{c.title}</div>
            <div className="muted mt-0.5 text-xs leading-relaxed">{c.outline}</div>
            {c.hook ? <div className="mt-1 text-xs text-emerald-400">钩子：{c.hook}</div> : null}
            {c.conflict ? <div className="mt-0.5 text-xs text-red-400/90">冲突：{c.conflict}</div> : null}
          </div>
        ));
        const arc = o.arc || {};
        const isOpen = open[n.id];
        return (
          <section key={n.id} className="panel overflow-hidden">
            <div className="flex cursor-pointer items-center justify-between gap-3 px-5 py-4" onClick={() => toggle(n.id)}>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-base font-bold">{n.title}</h3>
                  <span className={`chip ${n.status === "publishing" ? "chip-ok" : n.status === "planning" ? "chip-warn" : "chip-info"}`}>{n.status}</span>
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
              <div className="flex flex-col gap-4 border-t border-[#1a2332] px-5 py-4">
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

                {arc && (arc.start || arc.mid || arc.end) ? (
                  <Field label="当前剧情弧">
                    <div className="flex flex-col gap-1 text-xs">
                      {arc.start ? <div><span className="text-sky-400">开端：</span>{arc.start}</div> : null}
                      {arc.mid ? <div><span className="text-amber-400">发展：</span>{arc.mid}</div> : null}
                      {arc.end ? <div><span className="text-emerald-400">去向：</span>{arc.end}</div> : null}
                    </div>
                  </Field>
                ) : null}

                {chs.length ? (
                  <Field label="本章细纲（两章）">
                    <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">{chs}</div>
                  </Field>
                ) : null}

                {o.foreshadowing || o.payoffs ? (
                  <Field label="伏笔台账">
                    <div className="flex flex-col gap-1 text-xs">
                      {(o.foreshadowing || []).map((f, i) => (
                        <div key={i}><span className="text-amber-400">埋：</span>{typeof f === "string" ? f : JSON.stringify(f)}</div>
                      ))}
                      {(o.payoffs || []).map((p, i) => (
                        <div key={i}><span className="text-emerald-400">收：</span>{typeof p === "string" ? p : JSON.stringify(p)}</div>
                      ))}
                    </div>
                  </Field>
                ) : null}

                <div className="muted text-xs">书 ID：{n.book_id || "未关联"} · 番茄章节 ID 见章节管理</div>
              </div>
            ) : null}
          </section>
        );
      })}
    </div>
  );
}
