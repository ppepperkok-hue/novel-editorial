const { app, BrowserWindow, ipcMain } = require("electron");
const { spawn } = require("node:child_process");
const net = require("node:net");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..");
const PYTHONW = "C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python311\\pythonw.exe";
const API_PORT = 8000;
let apiProc = null;
let win = null;

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
  apiProc = spawn(
    PYTHONW,
    ["-m", "novel_pipeline.web_api", "--db", "demo.db", "--port", String(API_PORT)],
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
  win.on("closed", () => {
    win = null;
    if (apiProc) {
      apiProc.kill();
      apiProc = null;
    }
  });
}

app.whenReady().then(async () => {
  try {
    await ensureApi();
  } catch (e) {
    console.error(e);
    app.quit();
    return;
  }
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  app.quit();
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
