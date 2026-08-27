import { describe, expect, it } from "vitest";

import { groupMotivesByOwner, parseMotiveText } from "./motiveText";

describe("parseMotiveText", () => {
  it("parses CLI-aligned motive lines into entries", () => {
    const entries = parseMotiveText(
      "m1 [总编] [ambition] strength=0.8 source=对话 touched=2026-08-28T10:00:00 带出一本连载",
    );
    expect(entries).toEqual([
      {
        id: "m1",
        owner: "总编",
        kind: "ambition",
        strength: "0.8",
        source: "对话",
        touched: "2026-08-28T10:00:00",
        content: "带出一本连载",
      },
    ]);
  });

  it("skips empty and unrecognized lines", () => {
    const entries = parseMotiveText(
      "no motives yet\nm1 [总编] [ambition] strength=0.8 source=对话 touched=2026-08-28T10:00:00 带出一本连载",
    );
    expect(entries).toHaveLength(1);
  });

  it("groups entries by owner preserving the report order", () => {
    const groups = groupMotivesByOwner(
      parseMotiveText(
        "m1 [总编] [ambition] strength=0.8 source=对话 touched=2026-08-28T10:00:00 带出一本连载\nm2 [写手] [pride] strength=0.6 source=写作 touched=2026-08-28T09:00:00 想写出代表作",
      ),
    );
    expect(groups.map((group) => group.owner)).toEqual(["总编", "写手"]);
    expect(groups[0].motives[0].id).toBe("m1");
  });
});
