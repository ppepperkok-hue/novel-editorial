function Row({ label, children }) {
  return (
    <div className="flex gap-2 border-b border-dashed border-slate-800 py-1.5 text-sm">
      <span className="muted w-20 shrink-0">{label}</span>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

function CharacterCard({ c }) {
  return (
    <div className="border-b border-dashed border-slate-800 py-1.5 text-sm last:border-0">
      <span className="font-semibold text-sky-400">{c.name}</span>
      <span className="muted ml-2 text-xs">{c.role}</span>
      <div className="muted text-xs">
        {c.personality || c.identity || ""}
        {c.speech_style ? ` · 口吻：${c.speech_style}` : ""}
        {c.current_state ? ` · 状态：${c.current_state}` : ""}
      </div>
    </div>
  );
}

export default function WorksSection({ novels }) {
  if (!novels?.length) {
    return <div className="panel p-4 muted text-sm">暂无作品，等待第一次运行记录。</div>;
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
          <div key={i} className="muted text-xs">
            {r.from} — {r.relation || ""} — {r.to}
            {r.note ? `：${r.note}` : ""}
          </div>
        ));
        const rules = (bible.world_rules || []).map((w, i) => (
          <div key={i} className="muted text-xs">· {w}</div>
        ));
        const chs = [o.chapter1, o.chapter2].filter(Boolean).map((c) => (
          <div key={c.title} className="py-1 text-sm">
            <span className="text-amber-400">{c.title}</span>
            <div className="muted text-xs">{c.outline}</div>
            {c.hook ? <div className="muted text-xs">钩子：{c.hook}</div> : null}
          </div>
        ));
        return (
          <div key={n.id} className="panel p-4">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <h3 className="text-base font-semibold">{n.title}</h3>
              <span className="badge-ok text-xs">{n.status}</span>
              <span className="muted text-xs">{n.platform} · {n.genre}</span>
              <span className="muted text-xs">
                章节 {n.chapters} · 已发布 {n.published}
              </span>
              {n.last_chapter_title ? (
                <span className="muted text-xs">最新章节：{n.last_chapter_title}</span>
              ) : null}
            </div>
            <div className="mb-2 text-sm text-slate-300">{n.abstract || n.premise}</div>
            <div className="mb-2 flex flex-wrap gap-1.5">
              {(n.tags || []).map((t) => (
                <span key={t} className="rounded-full bg-slate-800 px-2 py-0.5 text-xs">{t}</span>
              ))}
            </div>
            <details className="group">
              <summary className="cursor-pointer text-sm text-sky-400">查看大纲 / 主角 / 简介</summary>
              <div className="mt-2 rounded-lg border border-slate-800 bg-slate-950 p-3">
                <Row label="简介">{n.abstract || n.premise || "暂无"}</Row>
                {chars.length ? <Row label="主角">{chars}</Row> : null}
                {bibleChars.length ? <Row label="角色卡">{bibleChars}</Row> : null}
                {rels.length ? <Row label="人物关系">{rels}</Row> : null}
                {rules.length ? <Row label="世界观规则">{rules}</Row> : null}
                {n.premise ? <Row label="核心创意">{n.premise}</Row> : null}
                {n.volume_goal ? <Row label="卷目标">{n.volume_goal}</Row> : null}
                {o.keywords ? <Row label="关键词">{o.keywords}</Row> : null}
                {chs.length ? <Row label="本章大纲">{chs}</Row> : null}
              </div>
            </details>
          </div>
        );
      })}
    </div>
  );
}
