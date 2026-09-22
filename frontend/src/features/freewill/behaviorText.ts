/**
 * Parsers for the editorial CLI's free-will text reports.
 *
 * ``behavior timeline`` lines look like:
 *   2026-09-22T06:02:59 [impression] 责编 -> 沈夜: 开场人物的第一印象… | source=试读第一章
 * ``behavior show`` groups by partner:
 *   [责编]
 *     impression -> 沈夜: 开场人物的第一印象…
 *
 * Parsing keeps the raw text as the CLI-fidelity fallback; the parsed shape
 * only feeds the structured rendering.
 */

export interface TimelineEntry {
  at: string;
  kind: string;
  actor: string;
  target: string;
  content: string;
  source: string;
}

export interface BehaviorStateEntry {
  actor: string;
  kind: string;
  target: string;
  content: string;
}

const TIMELINE_RE =
  /^(\S+)\s+\[(\w+)\]\s+(\S+)\s+->\s+([^:]+):\s*(.*?)(?:\s*\|\s*source=(.*))?$/;

const STATE_LINE_RE = /^\s+(\w+)\s+->\s+([^:]+):\s*(.*)$/;
const ACTOR_RE = /^\[([^\]]+)\]\s*$/;

export function parseTimelineText(text: string): TimelineEntry[] {
  const entries: TimelineEntry[] = [];
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (line === "") {
      continue;
    }
    const match = TIMELINE_RE.exec(line);
    if (match === null) {
      continue;
    }
    entries.push({
      at: match[1],
      kind: match[2],
      actor: match[3],
      target: match[4].trim(),
      content: match[5].trim(),
      source: (match[6] ?? "").trim(),
    });
  }
  return entries;
}

export function parseBehaviorStateText(text: string): BehaviorStateEntry[] {
  const entries: BehaviorStateEntry[] = [];
  let actor = "";
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trimEnd();
    if (line.trim() === "") {
      continue;
    }
    const actorMatch = ACTOR_RE.exec(line.trim());
    if (actorMatch !== null) {
      actor = actorMatch[1].trim();
      continue;
    }
    const stateMatch = STATE_LINE_RE.exec(line);
    if (stateMatch !== null && actor !== "") {
      entries.push({
        actor,
        kind: stateMatch[1],
        target: stateMatch[2].trim(),
        content: stateMatch[3].trim(),
      });
    }
  }
  return entries;
}

export function groupBehaviorStateByActor(
  entries: BehaviorStateEntry[],
): Array<{ actor: string; entries: BehaviorStateEntry[] }> {
  const order: string[] = [];
  const byActor = new Map<string, BehaviorStateEntry[]>();
  for (const entry of entries) {
    if (!byActor.has(entry.actor)) {
      byActor.set(entry.actor, []);
      order.push(entry.actor);
    }
    byActor.get(entry.actor)?.push(entry);
  }
  return order.map((actor) => ({
    actor,
    entries: byActor.get(actor) ?? [],
  }));
}

const KIND_LABELS: Record<string, string> = {
  impression: "印象",
  relationship: "关系",
  viewpoint: "观点",
  silence: "沉默",
  conflict: "冲突",
  cooldown: "冷却",
};

export function behaviorKindLabel(kind: string): string {
  return KIND_LABELS[kind] ?? kind;
}
