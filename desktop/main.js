const { app, BrowserWindow, dialog, ipcMain, Menu, Notification, Tray, nativeImage } = require("electron");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");

const { autoUpdater } = require("electron-updater");

const isPackaged = app.isPackaged;
const ROOT = isPackaged
  ? path.join(process.resourcesPath, "novel-pipeline")
  : path.resolve(__dirname, "..");
// Portable: override with PYTHONW_EXE (absolute path) or rely on PATH lookup.
const PYTHONW = process.env.PYTHONW_EXE || "pythonw";
const API_PORT = 8000;
let apiProc = null;
let win = null;
let tray = null;
const notifiedExecKeys = new Set();
let notifTimer = null;
let apiStopping = false;
let apiRestartCount = 0;
const API_RESTART_MAX = 3;
const API_RESTART_DELAY_MS = 3000;
let startupReady = false;
let showRequested = false;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function notifyIssue(body) {
  if (!Notification.isSupported()) return;
  new Notification({ title: "小说流水线", body }).show();
}

function apiReady(port) {
  return new Promise((resolve) => {
    const req = http.get(
      { host: "127.0.0.1", port, path: "/api/control", timeout: 3000 },
      (res) => {
        let body = "";
        res.on("data", (c) => (body += c));
        res.on("end", () => {
          try {
            const j = JSON.parse(body);
            resolve(Boolean(j && j.scheduler));
          } catch {
            resolve(false);
          }
        });
      },
    );
    req.on("error", () => resolve(false));
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
  });
}

function userDbPath() {
  // Keep runtime data outside the install dir so NSIS upgrades never
  // overwrite the user's live database; seed from the bundled demo.db only
  // on first launch.
  const dbPath = path.join(app.getPath("userData"), "demo.db");
  const seedDb = path.join(ROOT, "demo.db");
  if (!fs.existsSync(dbPath) && fs.existsSync(seedDb)) {
    fs.mkdirSync(path.dirname(dbPath), { recursive: true });
    fs.copyFileSync(seedDb, dbPath);
  }
  return dbPath;
}

function spawnApiProcess() {
  const dbPath = userDbPath();
  const child = spawn(
    PYTHONW,
    ["-m", "novel_editorial.web_api", "--db", dbPath, "--port", String(API_PORT)],
    { cwd: ROOT, stdio: "ignore" },
  );
  apiProc = child;
  let spawnFailed = false;
  child.on("error", (err) => {
    spawnFailed = true;
    apiProc = null;
    const msg = `无法启动后端服务（${PYTHONW}）：${(err && err.message) || err}`;
    console.error("pythonw spawn failed:", err);
    if (win) {
      win.webContents.send("api-error", msg);
    }
    notifyIssue(msg);
  });
  child.on("exit", (code, signal) => {
    if (spawnFailed || apiStopping) return;
    apiProc = null;
    const reason = `后端服务异常退出（code=${code}${signal ? `, signal=${signal}` : ""}）`;
    console.error(reason);
    if (win) {
      win.webContents.send("api-error", reason);
    }
    if (apiRestartCount >= API_RESTART_MAX) {
      notifyIssue(`后端服务异常退出，自动重启已达上限（${API_RESTART_MAX} 次），请重启应用。`);
      return;
    }
    apiRestartCount += 1;
    notifyIssue(`${reason}，正在自动重启（${apiRestartCount}/${API_RESTART_MAX}）`);
    setTimeout(() => {
      if (apiStopping) return;
      spawnApiProcess();
    }, API_RESTART_DELAY_MS);
  });
  return child;
}

async function ensureApi() {
  if (await apiReady(API_PORT)) return;
  const child = spawnApiProcess();
  await new Promise((resolve, reject) => {
    child.once("spawn", () => resolve());
    child.once("error", (err) => {
      reject(new Error(`pythonw spawn failed: ${(err && err.message) || err}`));
    });
  });
  for (let i = 0; i < 40; i += 1) {
    if (await apiReady(API_PORT)) return;
    await sleep(500);
  }
  throw new Error("API service did not start or port 8000 is occupied by another service");
}

function createWindow() {
  if (win) {
    if (win.isMinimized()) win.restore();
    win.show();
    win.focus();
    return;
  }
  win = new BrowserWindow({
    width: 1320,
    height: 880,
    minWidth: 1080,
    minHeight: 720,
    frame: false,
    backgroundColor: "#1a1a1a",
    show: false,
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  win.once("ready-to-show", () => win.show());
  win.loadURL(`http://127.0.0.1:${API_PORT}/`);
  win.on("close", (e) => {
    // Closing the window hides to tray unless the app is quitting.
    if (!app.isQuiting) {
      e.preventDefault();
      win.hide();
    }
  });
  win.on("closed", () => {
    win = null;
    apiStopping = true;
    if (apiProc) {
      apiProc.kill();
      apiProc = null;
    }
  });
}

function showWindow() {
  if (!win) {
    if (!startupReady) {
      showRequested = true;
      return;
    }
    createWindow();
    return;
  }
  if (win.isMinimized()) win.restore();
  win.show();
  win.focus();
}

function panelToken() {
  // Mirror web_api._panel_token(): process env wins, then ~/.n8n/.env.
  if (process.env.PANEL_TOKEN) return process.env.PANEL_TOKEN.trim();
  try {
    const envPath = path.join(os.homedir(), ".n8n", ".env");
    for (const line of fs.readFileSync(envPath, "utf8").split(/\r?\n/)) {
      if (!line.includes("=")) continue;
      const eq = line.indexOf("=");
      if (line.slice(0, eq).trim() === "PANEL_TOKEN") {
        return line.slice(eq + 1).trim();
      }
    }
  } catch {
    // env file missing: token auth is off
  }
  return "";
}

async function triggerWorkflow(workflow) {
  const label = workflow === "daily" ? "日更" : "周会";
  try {
    const headers = { "Content-Type": "application/json" };
    const token = panelToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    const r = await fetch(`http://127.0.0.1:${API_PORT}/api/control`, {
      method: "POST",
      headers,
      body: JSON.stringify({ action: "run_now", workflow }),
    });
    const data = await r.json();
    if (data.ok) {
      if (Notification.isSupported()) {
        new Notification({
          title: "小说流水线",
          body: `${label}已启动，正在后台执行`,
        }).show();
      }
    } else {
      if (Notification.isSupported()) {
        new Notification({
          title: "小说流水线",
          body: `${label}启动失败：${data.error || "未知"}`,
        }).show();
      }
    }
  } catch (e) {
    console.error("trigger failed", e);
    notifyIssue(`${label}启动失败：${(e && e.message) || e}`);
  }
}

function createTray() {
  const icon = nativeImage.createFromPath(path.join(__dirname, "assets", "tray.png"));
  tray = new Tray(icon);
  tray.setToolTip("小说流水线");
  const menu = Menu.buildFromTemplate([
    { label: "打开控制台", click: showWindow },
    { type: "separator" },
    { label: "立即更新一章", click: () => triggerWorkflow("daily") },
    { label: "立即跑架构师周会", click: () => triggerWorkflow("weekly") },
    { type: "separator" },
    { label: "退出", click: () => {
      app.isQuiting = true;
      app.quit();
    } },
  ]);
  tray.setContextMenu(menu);
  tray.on("double-click", showWindow);
}

function watchExecutions() {
  const terminalStates = ["success", "error", "failed", "crashed", "partial"];
  let historySeeded = false;
  const markHistory = (list) => {
    for (const exec of list) {
      if (!terminalStates.includes(exec.status)) continue;
      notifiedExecKeys.add(`${exec.workflow}-${exec.id}-${exec.status}`);
    }
  };
  const fetchList = async () => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000);
    try {
      const r = await fetch(`http://127.0.0.1:${API_PORT}/api/executions`, {
        signal: controller.signal,
      });
      const data = await r.json();
      return data.executions || [];
    } finally {
      clearTimeout(timer);
    }
  };
  // Executions already terminal at startup count as known, so only
  // transitions observed during this run produce notifications.
  fetchList()
    .then((list) => {
      markHistory(list);
      historySeeded = true;
    })
    .catch(() => {});
  let pollingInFlight = false;
  notifTimer = setInterval(async () => {
    if (pollingInFlight) return;
    pollingInFlight = true;
    try {
      const list = await fetchList();
      if (!historySeeded) {
        // Startup snapshot failed; suppress history on the first successful poll.
        markHistory(list);
        historySeeded = true;
        return;
      }
      for (const exec of list) {
        if (!terminalStates.includes(exec.status)) continue;
        const key = `${exec.workflow}-${exec.id}-${exec.status}`;
        if (notifiedExecKeys.has(key)) continue;
        notifiedExecKeys.add(key);
        if (!Notification.isSupported()) continue;
        const outcome =
          exec.status === "success" ? "成功" : exec.status === "partial" ? "部分成功" : "失败";
        new Notification({
          title: "小说流水线",
          body: `${exec.workflow}执行${outcome}（#${exec.id}）`,
        }).show();
      }
    } catch (e) {
      // API temporarily unavailable; keep polling
    } finally {
      pollingInFlight = false;
    }
  }, 30000);
}

function setupAutoUpdater() {
  if (!isPackaged) return;
  autoUpdater.autoDownload = true;
  autoUpdater.on("update-downloaded", () => {
    if (Notification.isSupported()) {
      new Notification({
        title: "小说流水线",
        body: "新版本已下载，重启应用即可安装",
      }).show();
    }
  });
  autoUpdater.checkForUpdatesAndNotify().catch(() => {});
}

app.whenReady().then(async () => {
  const gotLock = app.requestSingleInstanceLock();
  if (!gotLock) {
    app.quit();
    return;
  }
  app.on("second-instance", () => {
    showWindow();
  });
  try {
    await ensureApi();
  } catch (e) {
    console.error(e);
    apiStopping = true;
    dialog.showErrorBox(
      "文学编辑部启动失败",
      String((e && e.message) || e) +
        "\n\n请确认 Python（pythonw）已安装且端口 8000 未被占用，然后重新启动应用。",
    );
    app.isQuiting = true;
    app.quit();
    return;
  }
  createWindow();
  startupReady = true;
  if (showRequested) {
    showRequested = false;
    showWindow();
  }
  createTray();
  watchExecutions();
  setupAutoUpdater();
  app.on("activate", () => {
    showWindow();
  });
});

app.on("window-all-closed", () => {
  // Keep running in the tray; quit happens via tray menu or explicit close.
});

ipcMain.on("win:minimize", (e) => {
  BrowserWindow.fromWebContents(e.sender)?.minimize();
});

ipcMain.on("win:maximize", (e) => {
  const w = BrowserWindow.fromWebContents(e.sender);
  if (!w) return;
  if (w.isMaximized()) w.unmaximize();
  else w.maximize();
});

ipcMain.on("win:close", (e) => {
  BrowserWindow.fromWebContents(e.sender)?.close();
});

ipcMain.handle("win:is-maximized", (e) => {
  return BrowserWindow.fromWebContents(e.sender)?.isMaximized() ?? false;
});

ipcMain.handle("app:set-auto-launch", (e, enabled) => {
  app.setLoginItemSettings({ openAtLogin: Boolean(enabled) });
  return app.getLoginItemSettings().openAtLogin;
});

ipcMain.handle("app:get-auto-launch", () => {
  return app.getLoginItemSettings().openAtLogin;
});

ipcMain.on("app:close-to-tray", () => {
  if (win) {
    win.hide();
  }
});

ipcMain.on("app:quit", () => {
  app.isQuiting = true;
  app.quit();
});
