import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SettingsPage from "../components/SettingsPage.jsx";

const control = {
  settings: {
    daily_enabled: "true",
    monthly_budget: "100",
    target_words: "2000",
    style_tweak: "",
    daily_run_time: "08:00",
    daily_chapters: "2",
    target_chapters: "0",
    novel_premise: "",
    novel_keywords: "",
    novel_genre: "",
  },
  scheduler: {
    enabled: true,
    scheduled_time: "08:00",
    last_run: null,
  },
};

function jsonResponse(data) {
  return { ok: true, json: async () => data };
}

function renderPage(pushToast = vi.fn()) {
  render(
    <SettingsPage
      data={{}}
      onRefresh={vi.fn()}
      pushToast={pushToast}
      theme="dark"
      onThemeChange={vi.fn()}
    />,
  );
  return pushToast;
}

describe("SettingsPage", () => {
  let posts;

  beforeEach(() => {
    posts = [];
    global.fetch = vi.fn(async (url, init) => {
      if (init?.method === "POST") {
        const body = JSON.parse(init.body);
        posts.push(body);
        if (body.action === "save_settings") {
          return jsonResponse({ ok: true, saved: body.settings });
        }
        if (body.action === "apply_schedule") {
          return jsonResponse({ ok: false, deploy: { output: "权限不足" }, error: "" });
        }
        return jsonResponse({ ok: true });
      }
      return jsonResponse(control);
    });
  });

  it("renders the control and run settings after loading", async () => {
    renderPage();
    expect(await screen.findByText("启用每日自动更新")).toBeInTheDocument();
    expect(screen.getByText("流程控制")).toBeInTheDocument();
    expect(screen.getByText("运行设置")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /保存设置/ })).toBeEnabled();
  });

  it("shows a failure toast when saving settings fails", async () => {
    global.fetch = vi.fn(async (url, init) => {
      if (init?.method === "POST") {
        const body = JSON.parse(init.body);
        if (body.action === "save_settings") {
          return jsonResponse({ ok: false, error: "余额不足" });
        }
        return jsonResponse({ ok: true });
      }
      return jsonResponse(control);
    });
    const pushToast = renderPage();
    await screen.findByText("启用每日自动更新");
    fireEvent.click(screen.getByRole("button", { name: /保存设置/ }));
    await waitFor(() =>
      expect(pushToast).toHaveBeenCalledWith("保存失败：余额不足", "bad"),
    );
  });

  it("surfaces scheduled-task registration failure after settings are saved", async () => {
    const pushToast = renderPage();
    await screen.findByText("启用每日自动更新");
    fireEvent.click(screen.getByRole("button", { name: /保存设置/ }));
    await waitFor(() =>
      expect(pushToast).toHaveBeenCalledWith(
        "设置已保存，但计划任务注册失败：权限不足",
        "bad",
      ),
    );
    expect(posts.map((p) => p.action)).toEqual(["save_settings", "apply_schedule"]);
  });
});
