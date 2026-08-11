import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ChaptersPage from "../components/ChaptersPage.jsx";

const data = {
  novels: [{ id: 1, title: "测试书" }],
  chapters: [
    {
      id: 7,
      novel_id: 1,
      seq: 3,
      title: "第三章",
      status: "published",
      words: 2000,
      score: 88,
      outline: "章纲",
      fanqie_item_id: "x",
      published_at: "2026-08-10 10:00:00",
    },
  ],
};

describe("ChaptersPage reader", () => {
  beforeEach(() => {
    global.fetch = vi.fn(async (url) => {
      if (String(url).includes("/api/chapter_content")) {
        return {
          ok: true,
          json: async () => ({
            chapter_id: 7,
            content: "第一段正文。\n\n第二段正文。",
            updated_at: "",
          }),
        };
      }
      return { ok: true, json: async () => ({}) };
    });
  });

  it("opens the reader and shows chapter paragraphs", async () => {
    render(<ChaptersPage data={data} />);
    fireEvent.click(screen.getByText("阅读"));
    expect(await screen.findByText("第一段正文。")).toBeInTheDocument();
    expect(screen.getByText("第二段正文。")).toBeInTheDocument();
  });

  it("shows a friendly empty state when content is not stored", async () => {
    global.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({ chapter_id: 7, content: "", updated_at: "" }),
    }));
    render(<ChaptersPage data={data} />);
    fireEvent.click(screen.getByText("阅读"));
    expect(await screen.findByText(/正文未落库/)).toBeInTheDocument();
  });

  it("shows editorial quality notes when present", async () => {
    const withNotes = {
      ...data,
      chapters: [
        {
          ...data.chapters[0],
          quality_notes: JSON.stringify({
            review: "逻辑没问题，结尾略平",
            reader: "开头会追，中段想跳",
          }),
        },
      ],
    };
    render(<ChaptersPage data={withNotes} />);
    fireEvent.click(screen.getByText("阅读"));
    expect(await screen.findByText("编辑部评语")).toBeInTheDocument();
    expect(screen.getByText(/逻辑没问题，结尾略平/)).toBeInTheDocument();
    expect(screen.getByText(/开头会追，中段想跳/)).toBeInTheDocument();
  });
});
