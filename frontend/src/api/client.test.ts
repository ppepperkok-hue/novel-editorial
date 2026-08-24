import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  createAuthorDraft,
  createWorkspace,
  generateDraft,
  getConfig,
  getDraft,
  getDraftDiff,
  getDrafts,
  getGlobalEvents,
  getInspect,
  getLog,
  getOverview,
  getPending,
  getReviews,
  getStyle,
  getStructure,
  getWorkspace,
  listTalk,
  listTemplates,
  listWorks,
  postDecision,
  reviseDraft,
  saveDraftContent,
  sendTalk,
} from "./client";

const fetchMock = vi.fn();

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function textResponse(body: string, status = 200): Response {
  return new Response(body, {
    status,
    headers: { "Content-Type": "text/plain" },
  });
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  fetchMock.mockReset();
});

describe("api client contract parsing", () => {
  it("getConfig parses the panel poll interval", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ panel_poll_interval: 5 }));

    await expect(getConfig()).resolves.toEqual({ panel_poll_interval: 5 });
    expect(fetchMock).toHaveBeenCalledWith(
      "/config",
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
  });

  it("getOverview parses the cross-workspace overview", async () => {
    const body = {
      overviews: [
        {
          workspace_id: "w1",
          title: "甲书",
          genre: "网文",
          status: "writing",
          pending_count: 1,
          structure: "1/3 章",
          last_activity: "2026-08-22T10:00:00+00:00",
          created_at: "2026-08-01T00:00:00+00:00",
        },
      ],
      total: 1,
      skipped: 0,
    };
    fetchMock.mockResolvedValueOnce(jsonResponse(body));

    const overview = await getOverview();
    expect(overview.total).toBe(1);
    expect(overview.skipped).toBe(0);
    expect(overview.overviews[0]).toMatchObject({
      workspace_id: "w1",
      title: "甲书",
      pending_count: 1,
    });
  });

  it("listWorks parses workspace summaries", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse([
        {
          id: "w1",
          title: "甲书",
          genre: "网文",
          description: "一部连载",
          status: "writing",
          created_at: "2026-08-01T00:00:00+00:00",
        },
      ]),
    );

    const works = await listWorks();
    expect(works[0]).toMatchObject({
      id: "w1",
      title: "甲书",
      status: "writing",
    });
    expect(fetchMock.mock.calls[0][0]).toBe("/works");
  });

  it("getWorkspace parses the detail with its band profile", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        id: "w1",
        title: "甲书",
        genre: "网文",
        description: "",
        status: "writing",
        created_at: "2026-08-01T00:00:00+00:00",
        band: [
          {
            id: "a1",
            name: "总编",
            role: "editor_in_chief",
            personality: "网感敏锐",
            stance: "留存优先",
            values: "更新稳定",
            aesthetic: "高信息密度",
            emotion_baseline: "稳定",
            mood: "干劲十足",
            work_habits: "盯章节末钩子",
            weaknesses: "铺垫压薄",
            relationship_presets: "盯写手最紧",
            private_motive: "带出一本连载",
            created_at: "2026-08-01T00:00:00+00:00",
          },
        ],
      }),
    );

    const detail = await getWorkspace("w1");
    expect(detail.title).toBe("甲书");
    expect(detail.band[0]).toMatchObject({
      name: "总编",
      role: "editor_in_chief",
    });
    expect(fetchMock.mock.calls[0][0]).toBe("/works/w1");
  });

  it("createWorkspace posts the generated body type as JSON", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        {
          id: "w2",
          title: "乙书",
          genre: "同人",
          description: "",
          status: "writing",
          created_at: "2026-08-02T00:00:00+00:00",
        },
        201,
      ),
    );

    const created = await createWorkspace({
      title: "乙书",
      genre: "同人",
      description: "",
    });
    expect(created).toEqual({
      id: "w2",
      title: "乙书",
      genre: "同人",
      description: "",
      status: "writing",
      created_at: "2026-08-02T00:00:00+00:00",
    });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/works");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({
      title: "乙书",
      genre: "同人",
      description: "",
    });
  });

  it("listTemplates parses template names and descriptions", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse([
        { name: "网文", description: "节奏快、钩子密" },
        { name: "正统", description: "结构完整" },
      ]),
    );

    const templates = await listTemplates();
    expect(templates).toHaveLength(2);
    expect(templates[0]).toEqual({
      name: "网文",
      description: "节奏快、钩子密",
    });
    expect(fetchMock.mock.calls[0][0]).toBe("/templates");
  });

  it("getGlobalEvents parses events and skipped count", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        events: [
          {
            id: "e1",
            workspace_id: "w1",
            type: "draft.created",
            time: "2026-08-22T10:00:00+00:00",
            actor: "写手",
            payload: { draft_id: "d1" },
          },
        ],
        skipped: 0,
      }),
    );

    const body = await getGlobalEvents();
    expect(body.skipped).toBe(0);
    expect(body.events[0].type).toBe("draft.created");
    expect(body.events[0].payload).toEqual({ draft_id: "d1" });
  });

  it("getPending parses the pending draft list", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse([
        {
          id: "d1",
          title: "第一章",
          status: "draft",
          current_version: 1,
          updated_at: "2026-08-22T10:00:00+00:00",
        },
      ]),
    );

    const pending = await getPending("w1");
    expect(pending[0]).toMatchObject({ id: "d1", title: "第一章" });
    expect(fetchMock.mock.calls[0][0]).toBe("/works/w1/pending");
  });

  it("getDrafts parses draft summaries", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse([
        {
          id: "d1",
          title: "第一章",
          status: "accepted",
          current_version: 2,
          updated_at: "2026-08-22T10:00:00+00:00",
        },
      ]),
    );

    const drafts = await getDrafts("w1");
    expect(drafts[0]).toMatchObject({ id: "d1", current_version: 2 });
  });

  it("getDraft parses the detail with version history", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        id: "d1",
        title: "第一章",
        status: "draft",
        current_version: 2,
        created_at: "2026-08-01T00:00:00+00:00",
        updated_at: "2026-08-22T10:00:00+00:00",
        versions: [
          {
            version: 1,
            actor: "写手",
            reason: "initial",
            created_at: "2026-08-01T00:00:00+00:00",
            content: "初版正文",
          },
        ],
      }),
    );

    const detail = await getDraft("w1", "d1");
    expect(detail.versions).toHaveLength(1);
    expect(detail.versions[0].actor).toBe("写手");
    expect(detail.versions[0].content).toBe("初版正文");
  });

  it("getDraftDiff requests both versions and returns plain text", async () => {
    fetchMock.mockResolvedValueOnce(
      textResponse("--- v1\n+++ v2\n-初版\n+修订版"),
    );

    const diff = await getDraftDiff("w1", "d1", {
      version_a: 1,
      version_b: 2,
    });
    expect(diff).toBe("--- v1\n+++ v2\n-初版\n+修订版");
    expect(fetchMock.mock.calls[0][0]).toBe(
      "/works/w1/drafts/d1/diff?version_a=1&version_b=2",
    );
    const [, init] = fetchMock.mock.calls[0];
    expect(init?.headers).toBeInstanceOf(Headers);
  });

  it("getDraftDiff passes through the generated query type and accepts no differences", async () => {
    fetchMock.mockResolvedValueOnce(textResponse("no differences"));

    await expect(
      getDraftDiff("w1", "d1", { version_a: 2, version_b: 2 }),
    ).resolves.toBe("no differences");
    expect(fetchMock.mock.calls[0][0]).toBe(
      "/works/w1/drafts/d1/diff?version_a=2&version_b=2",
    );
  });

  it("listTalk parses conversation items with the CLI-aligned mark and line", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse([
        {
          id: "m1",
          role: "author",
          actor: "作者",
          content: "这章钩子不够",
          payload: {},
          created_at: "2026-08-22T10:00:00+00:00",
          mark: null,
          line: "[author] 作者: 这章钩子不够",
        },
        {
          id: "m2",
          role: "agent",
          actor: "责编",
          content: "我来加个反转",
          payload: { disagreement: { mark: "开篇节奏" } },
          created_at: "2026-08-22T10:01:00+00:00",
          mark: "agent·分歧·开篇节奏",
          line: "[agent·分歧·开篇节奏] 责编: 我来加个反转",
        },
      ]),
    );

    const talk = await listTalk("w1");
    expect(talk).toHaveLength(2);
    expect(talk[0]).toMatchObject({
      role: "author",
      actor: "作者",
      mark: null,
      line: "[author] 作者: 这章钩子不够",
    });
    expect(talk[1].mark).toBe("agent·分歧·开篇节奏");
    expect(talk[1].line).toBe("[agent·分歧·开篇节奏] 责编: 我来加个反转");
    expect(fetchMock.mock.calls[0][0]).toBe("/works/w1/talk");
  });

  it("sendTalk posts the generated body type and parses the new messages", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        {
          messages: [
            {
              id: "m9",
              role: "author",
              actor: "作者",
              content: "把结局改圆一点",
              payload: {},
              created_at: "2026-08-22T11:00:00+00:00",
            },
          ],
        },
        201,
      ),
    );

    const result = await sendTalk("w1", { message: "把结局改圆一点" });
    expect(result.messages).toHaveLength(1);
    expect(result.messages[0]).toMatchObject({
      actor: "作者",
      content: "把结局改圆一点",
    });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/works/w1/talk");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({
      message: "把结局改圆一点",
    });
  });

  it("createAuthorDraft posts the title body and parses awaiting_decision", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        {
          id: "d9",
          title: "第三章",
          status: "draft",
          current_version: 0,
          updated_at: "2026-08-22T11:00:00+00:00",
          awaiting_decision: true,
        },
        201,
      ),
    );

    const created = await createAuthorDraft("w1", { title: "第三章" });
    expect(created).toMatchObject({
      id: "d9",
      current_version: 0,
      awaiting_decision: true,
    });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/works/w1/drafts/new");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({ title: "第三章" });
  });

  it("generateDraft posts an optional title to the generate endpoint", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        {
          id: "d10",
          title: "未命名章节",
          status: "draft",
          current_version: 1,
          updated_at: "2026-08-22T11:00:00+00:00",
          awaiting_decision: true,
        },
        201,
      ),
    );

    const generated = await generateDraft("w1", { title: "未命名章节" });
    expect(generated).toMatchObject({ id: "d10", current_version: 1 });
    expect(fetchMock.mock.calls[0][0]).toBe("/works/w1/drafts");
  });

  it("saveDraftContent PUTs content and the default reason", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        {
          id: "d1",
          title: "第一章",
          status: "draft",
          current_version: 2,
          updated_at: "2026-08-22T11:00:00+00:00",
          awaiting_decision: true,
        },
        200,
      ),
    );

    const saved = await saveDraftContent("w1", "d1", {
      content: "新正文",
      reason: "作者修改",
    });
    expect(saved).toMatchObject({ current_version: 2, awaiting_decision: true });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/works/w1/drafts/d1/content");
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(init?.body as string)).toEqual({
      content: "新正文",
      reason: "作者修改",
    });
  });

  it("reviseDraft posts the reason to the revise endpoint", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        {
          id: "d1",
          title: "第一章",
          status: "draft",
          current_version: 3,
          updated_at: "2026-08-22T11:00:00+00:00",
          awaiting_decision: true,
        },
        200,
      ),
    );

    const revised = await reviseDraft("w1", "d1", { reason: "按意见重写" });
    expect(revised).toMatchObject({ current_version: 3 });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/works/w1/drafts/d1/revise");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({ reason: "按意见重写" });
  });

  it("getReviews parses the review list", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse([
        {
          id: "r1",
          role: "agent",
          actor: "责编",
          content: "钩子再亮一点",
          created_at: "2026-08-22T10:00:00+00:00",
        },
      ]),
    );

    const reviews = await getReviews("w1", "d1");
    expect(reviews[0]).toMatchObject({ actor: "责编", content: "钩子再亮一点" });
    expect(fetchMock.mock.calls[0][0]).toBe("/works/w1/reviews?draft_id=d1");
  });

  it("getInspect returns plain text with the keyword query", async () => {
    fetchMock.mockResolvedValueOnce(textResponse("[风格]\n冷峻克制"));

    await expect(getInspect("w1", "冷峻")).resolves.toBe("[风格]\n冷峻克制");
    expect(fetchMock.mock.calls[0][0]).toBe(
      "/works/w1/inspect?keyword=%E5%86%B7%E5%B3%BB",
    );
  });

  it("getLog returns plain text", async () => {
    fetchMock.mockResolvedValueOnce(textResponse("作品：《甲书》\n== 草稿 =="));

    await expect(getLog("w1")).resolves.toBe("作品：《甲书》\n== 草稿 ==");
    expect(fetchMock.mock.calls[0][0]).toBe("/works/w1/log");
  });

  it("getStyle and getStructure parse their contracts", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ description: "冷峻克制", forbidden_words: "宛如" }))
      .mockResolvedValueOnce(
        jsonResponse([
          {
            id: "n1",
            kind: "volume",
            title: "第一卷",
            parent_id: null,
            sort_order: 1,
            status: "writing",
            draft_id: null,
            created_at: "2026-08-01T00:00:00+00:00",
          },
        ]),
      );

    await expect(getStyle("w1")).resolves.toEqual({
      description: "冷峻克制",
      forbidden_words: "宛如",
    });
    const nodes = await getStructure("w1");
    expect(nodes[0]).toMatchObject({ kind: "volume", title: "第一卷" });
  });

  it("postDecision sends the body as JSON", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: "d1", status: "accepted" }));

    await expect(
      postDecision("w1", { draft_id: "d1", action: "accept" }),
    ).resolves.toEqual({ id: "d1", status: "accepted" });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/works/w1/decisions");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({
      draft_id: "d1",
      action: "accept",
    });
    expect(init?.headers).toBeInstanceOf(Headers);
  });

  it("postDecision accepts a 201 response and exposes the resulting status", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ id: "d1", status: "accepted" }, 201),
    );

    const result = await postDecision("w1", {
      draft_id: "d1",
      action: "accept",
    });
    expect(result).toEqual({ id: "d1", status: "accepted" });
  });

  it("encodes workspace ids in paths", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([]));

    await getPending("w 1/2");
    expect(fetchMock.mock.calls[0][0]).toBe("/works/w%201%2F2/pending");
  });
});

describe("api client errors", () => {
  it("throws a readable error carrying path, status and API detail", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ detail: "draft not found: x" }, 404),
    );

    await expect(getDraft("w1", "x")).rejects.toThrow(
      "请求失败：404 /works/w1/drafts/x：draft not found: x",
    );
  });

  it("surfaces non-JSON error bodies with status and path", async () => {
    fetchMock.mockResolvedValueOnce(new Response("oops", { status: 500 }));

    await expect(getOverview()).rejects.toThrow("请求失败：500 /overview");
  });

  it("rejects on network failure", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));

    await expect(getGlobalEvents()).rejects.toThrow("Failed to fetch");
  });
});
