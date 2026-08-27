/**
 * Presentational parsing of the CLI-aligned motives report (GET
 * /works/{id}/motives). The raw text stays the source of truth; this only
 * extracts the per-motive fields the UI needs for grouping and dropping.
 */
export interface MotiveEntry {
  id: string;
  owner: string;
  kind: string;
  strength: string;
  source: string;
  touched: string;
  content: string;
}

const MOTIVE_LINE =
  /^(\S+) \[(.+?)\] \[(.+?)\] strength=(\S+) source=(\S+) touched=(\S+) (.*)$/;

export function parseMotiveText(text: string): MotiveEntry[] {
  return text.split("\n").flatMap((line) => {
    const match = MOTIVE_LINE.exec(line.trim());
    if (match === null) {
      return [];
    }
    return [
      {
        id: match[1],
        owner: match[2],
        kind: match[3],
        strength: match[4],
        source: match[5],
        touched: match[6],
        content: match[7],
      },
    ];
  });
}

/** Group motive entries by owner, keeping the report's order. */
export function groupMotivesByOwner(
  entries: MotiveEntry[],
): Array<{ owner: string; motives: MotiveEntry[] }> {
  const groups = new Map<string, MotiveEntry[]>();
  for (const entry of entries) {
    const list = groups.get(entry.owner) ?? [];
    list.push(entry);
    groups.set(entry.owner, list);
  }
  return Array.from(groups, ([owner, motives]) => ({ owner, motives }));
}
