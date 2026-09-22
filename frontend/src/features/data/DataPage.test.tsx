import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../../App";

const workspaceBody = {
  id: "w-a",
  title: "甲书",
  genre: "网文",
  description: "",
  status: "writing",
  created_at: "2026-08-01T00:00:00+00:00",
  band: [],
};

const configSnapshot = {
  data_dir: "/data",
  config_path: "/config.toml",
  llm_base_url: "https://api.deepseek.com",
  llm_model: "deepseek-chat",
  log_level: "INFO",
  quality_threshold: 8,
  memory_decay_per_day: 0.05,
  memory_rehearsal_boost: 1.0,
  memory_archive_threshold: 30,
  proactive_enabled: true,
  proactive_max_per_agent: 3,
  freedom_dial: 0.4,
  freedom_seed: 7,
  motive_llm_enabled: false,
  embedding_backend: "none",
  embedding_model: "",
  embedding_dim: 0,
  embedding_top_k: 5,
  api_host: "127.0.0.1",
  api_port: 8765,
  panel_poll_interval: 5,
  restart_required: false,
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderData(
  fetchMock: ReturnType<typeof vi.fn>,
  initialEntries = ["/works/w-a/data"],
) {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function baseRoutes() {
  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/works/w-a") {
      return Promise.resolve(jsonResponse(workspaceBody));
    }
    if (url === "/config" && init?.method === "PUT") {
      return Promise.resolve(
        jsonResponse({
          ...configSnapshot,
          restart_required: true,
          message: "config updated; api 重启后生效",
        }),
      );
    }
    if (url === "/config") {
      return Promise.resolve(jsonResponse(configSnapshot));
    }
    if (url.startsWith("/works/w-a/export")) {
      return Promise.resolve(
        new Response(new Blob(["zip"], { type: "application/zip" }), {
          status: 200,
          headers: {
            "Content-Type": "application/zip",
            "Content-Disposition":
              'attachment; filename="7178737e-20260922-011400.zip"',
          },
        }),
      );
    }
    if (url === "/works/import" && init?.method === "POST") {
      return Promise.resolve(
        jsonResponse(
          {
            id: "w-imported",
            title: "导入书",
            genre: "悬疑",
            description: "",
            status: "writing",
            created_at: "2026-09-22T00:00:00+00:00",
          },
          201,
        ),
      );
    }
    return Promise.reject(new Error(`未预期的请求：${url}`));
  });
}

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("data page", () => {
  it("renders the data page, config snapshot and the sidebar entry", async () => {
    const fetchMock = baseRoutes();
    renderData(fetchMock);

    await screen.findByTestId("config-snapshot");
    expect(screen.getByTestId("config-snapshot")).toHaveTextContent(
      "quality_threshold",
    );
    expect(screen.getByRole("link", { name: "数据" })).toHaveAttribute(
      "href",
      "/works/w-a/data",
    );
    expect(screen.getByTestId("export-panel")).toBeInTheDocument();
    expect(screen.getByTestId("import-panel")).toBeInTheDocument();
  });

  it("saves a whitelisted config key and shows the restart hint", async () => {
    const fetchMock = baseRoutes();
    renderData(fetchMock);

    await screen.findByTestId("config-snapshot");
    const panel = screen.getByTestId("config-panel");
    fireEvent.change(within(panel).getByPlaceholderText("数值"), {
      target: { value: "9" },
    });
    fireEvent.click(within(panel).getByRole("button", { name: "保存" }));

    const configUpdated = await screen.findByTestId("config-updated");
    expect(configUpdated.textContent).toBe("config updated; api 重启后生效");
    const put = fetchMock.mock.calls.find(
      ([url, init]) => String(url) === "/config" && init?.method === "PUT",
    );
    expect(JSON.parse(String(put?.[1]?.body))).toEqual({
      key: "quality_threshold",
      value: 9,
    });
  });

  it("blocks an out-of-range value without calling updateConfig and shows an alert", async () => {
    const fetchMock = baseRoutes();
    renderData(fetchMock);

    await screen.findByTestId("config-snapshot");
    const panel = screen.getByTestId("config-panel");
    fireEvent.change(within(panel).getByPlaceholderText("数值"), {
      target: { value: "-1" },
    });
    fireEvent.click(within(panel).getByRole("button", { name: "保存" }));

    const alert = await within(panel).findByRole("alert");
    expect(alert).toHaveTextContent("quality_threshold 必须是 ≥0 的整数");
    expect(
      fetchMock.mock.calls.some(
        ([url, init]) => String(url) === "/config" && init?.method === "PUT",
      ),
    ).toBe(false);
  });

  it("exports the workspace when the export button is clicked", async () => {
    const fetchMock = baseRoutes();
    renderData(fetchMock);

    await screen.findByTestId("config-snapshot");
    const createObjectURL = vi.fn(() => "blob:mock-url");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});

    fireEvent.click(screen.getByRole("button", { name: "导出 ZIP" }));

    await waitFor(() => {
      expect(click).toHaveBeenCalled();
    });
    expect(
      fetchMock.mock.calls.some(([url]) =>
        String(url).startsWith("/works/w-a/export"),
      ),
    ).toBe(true);
  });

  it("imports a zip and shows the resulting workspace", async () => {
    const fetchMock = baseRoutes();
    renderData(fetchMock);

    await screen.findByTestId("config-snapshot");
    const panel = screen.getByTestId("import-panel");
    const file = new File(["zip"], "archive.zip", { type: "application/zip" });
    fireEvent.change(within(panel).getByTestId("import-file-input"), {
      target: { files: [file] },
    });
    fireEvent.click(within(panel).getByRole("button", { name: "导入" }));

    const result = await within(panel).findByTestId("import-result");
    expect(result).toHaveTextContent("导入书");
    expect(result).toHaveTextContent("w-imported");
  });
});
