const { app, BrowserWindow, ipcMain, Menu, Notification, Tray, nativeImage } = require("electron");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const net = require("node:net");
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
let lastExecKey = "";
let notifTimer = null;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function portOpen(port) {
  return new Promise((resolve) => {
    const s = net.connect({ port, host: "127.0.0.1" });
    s.on("connect", () => {
      s.destroy();
      resolve(true);
    });
    s.on("error", () => resolve(false));
  });
}

async function ensureApi() {
  if (await portOpen(API_PORT)) return;
  const dbPath = isPackaged
    ? path.join(app.getPath("userData"), "demo.db")
    : path.join(ROOT, "demo.db");
  const srcDb = path.join(ROOT, "demo.db");
  if (isPackaged && fs.existsSync(srcDb) && !fs.existsSync(dbPath)) {
    fs.copyFileSync(srcDb, dbPath);
  }
  apiProc = spawn(
    PYTHONW,
    ["-m", "novel_pipeline.web_api", "--db", dbPath, "--port", String(API_PORT)],
    { cwd: ROOT, stdio: "ignore" },
  );
  for (let i = 0; i < 40; i += 1) {
    if (await portOpen(API_PORT)) return;
    await sleep(500);
  }
  throw new Error("API service did not start in time");
}

function createWindow() {
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
    if (apiProc) {
      apiProc.kill();
      apiProc = null;
    }
  });
}

function showWindow() {
  if (!win) {
    createWindow();
    return;
  }
  if (win.isMinimized()) win.restore();
  win.show();
  win.focus();
}

async function triggerWorkflow(workflow) {
  try {
    const r = await fetch(`http://127.0.0.1:${API_PORT}/api/control`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "run_now", workflow }),
    });
    const data = await r.json();
    const label = workflow === "daily" ? "日更" : "周会";
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
  notifTimer = setInterval(async () => {
    try {
      const r = await fetch(`http://127.0.0.1:${API_PORT}/api/executions`);
      const data = await r.json();
      const list = data.executions || [];
      if (!list.length) return;
      const first = list[0];
      const key = `${first.workflow}-${first.id}-${first.status}`;
      if (lastExecKey && lastExecKey !== key && ["success", "error", "failed", "crashed"].includes(first.status)) {
        if (Notification.isSupported()) {
          new Notification({
            title: "小说流水线",
            body: `${first.workflow}执行${first.status === "success" ? "成功" : "失败"}（#${first.id}）`,
          }).show();
        }
      }
      lastExecKey = key;
    } catch (e) {
      // API temporarily unavailable; keep polling
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
    ipcMain.handle("app:install-update", () => {
      autoUpdater.quitAndInstall();
    });
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
    app.quit();
    return;
  }
  createWindow();
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
