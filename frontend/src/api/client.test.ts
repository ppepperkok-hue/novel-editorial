import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  getConfig,
  getDraft,
  getDrafts,
  getGlobalEvents,
  getInspect,
  getLog,
  getOverview,
  getPending,
  getReviews,
  getStyle,
  getStructure,
  postDecision,
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
            reason: "initial",
            created_at: "2026-08-01T00:00:00+00:00",
            content: "初版正文",
          },
        ],
      }),
    );

    const detail = await getDraft("w1", "d1");
    expect(detail.versions).toHaveLength(1);
    expect(detail.versions[0].content).toBe("初版正文");
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
