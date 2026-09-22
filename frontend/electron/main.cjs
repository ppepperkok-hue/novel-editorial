'use strict';

// Electron 桌面壳主进程（FE-N）。
//
// 设计：web 同源。本进程只负责拉起后端（uv run novel-editorial api serve）、
// 轮询 /health 就绪后开 BrowserWindow 直连 http://127.0.0.1:{port}。前端界面
// 由后端托管 frontend/dist（见 create_app），这里不复制任何前端代码。

const { app, BrowserWindow, dialog, shell } = require('electron');
const { spawn } = require('child_process');
const http = require('http');
const fs = require('fs');
const path = require('path');

const isWin = process.platform === 'win32';

// 绑定地址与连接地址分离：NOVEL_API_HOST 只决定后端绑定地址（env 继承 process.env
// 传给 api serve，load_settings 读取）；桌面壳本地连接固定 127.0.0.1，避免把
// 0.0.0.0 之类绑定地址当连接地址而失败。默认 127.0.0.1:8765；config.toml 改了
// api_host/api_port 时，桌面壳需用同名环境变量保持一致（见 docs/usage.md 桌面壳节）。
const BIND_HOST = process.env.NOVEL_API_HOST || '127.0.0.1';
const API_PORT = (() => {
  const parsed = Number.parseInt(process.env.NOVEL_API_PORT, 10);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 8765;
})();
const BASE_URL = `http://127.0.0.1:${API_PORT}`;

const READY_TIMEOUT_MS = 30000;
const POLL_INTERVAL_MS = 500;

let mainWindow = null;
let backend = null;
let backendStopped = false;
let quitting = false;
let backendExitCode = null; // 后端退出码快照：backend 置 null 后仍可读（waitForReady 报错用）
let backendExitSignal = null; // 后端退出信号快照：code 为 null（被信号杀死）时用
let pendingFocus = false; // second-instance 早于窗口创建时置位，bootstrap 开窗后补聚焦

function log(...args) {
  // 主进程日志（stdout）；后端输出另加 [api] 前缀。
  console.log('[desktop]', ...args);
}

// —— 外链与同源判断 ——
function isHttpUrl(url) {
  return /^https?:/i.test(url);
}

// hostname 等价归一化：127.0.0.1 与 localhost 视为同源，其余精确比较。
function isEquivalentHostname(a, b) {
  if (a === b) return true;
  const norm = (h) => (h === '127.0.0.1' || h === 'localhost' ? 'localhost' : h);
  return norm(a) === norm(b);
}

// 同源判断：protocol + port 精确比较，hostname 做 localhost 等价归一化，堵住
// 127.0.0.1:87650 / 127.0.0.1:8765.evil.com 之类前缀绕过。解析失败按非同源处理。
function isSameOrigin(url) {
  try {
    const target = new URL(url);
    const base = new URL(BASE_URL);
    if (target.protocol !== base.protocol || target.port !== base.port) return false;
    return isEquivalentHostname(target.hostname, base.hostname);
  } catch {
    return false;
  }
}

function openExternal(url) {
  if (!isHttpUrl(url)) return;
  try {
    shell.openExternal(url);
  } catch (err) {
    log('openExternal 失败：', err.message);
  }
}

// 定位项目根：优先 NOVEL_APP_ROOT；否则从 exe 所在目录（打包态）或 app.getAppPath()
// 逐级上溯，找到含 pyproject.toml 的目录。
function findProjectRoot() {
  const envRoot = process.env.NOVEL_APP_ROOT;
  if (envRoot) {
    const resolved = path.resolve(envRoot);
    if (fs.existsSync(path.join(resolved, 'pyproject.toml'))) {
      return resolved;
    }
    log(`NOVEL_APP_ROOT 指向的目录缺少 pyproject.toml：${resolved}，回退自动上溯`);
  }

  const starts = [];
  if (app.isPackaged) {
    // exe 所在目录（portable 放进项目根即可被上溯定位）。
    starts.push(path.dirname(process.execPath));
  }
  // 开发态（electron .）app.getAppPath() 为 frontend/electron；打包态为 app.asar。
  starts.push(app.getAppPath());

  for (const start of starts) {
    const found = walkUpForPyproject(start);
    if (found) return found;
  }
  return null;
}

function walkUpForPyproject(start) {
  let dir = path.resolve(start);
  try {
    if (fs.existsSync(dir) && fs.statSync(dir).isFile()) {
      dir = path.dirname(dir); // app.asar 是文件，取其所在目录
    }
  } catch {
    return null;
  }
  for (;;) {
    if (fs.existsSync(path.join(dir, 'pyproject.toml'))) return dir;
    const parent = path.dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
}

function startBackend(projectRoot) {
  const args = ['run', 'novel-editorial', 'api', 'serve'];
  log(`启动后端：uv ${args.join(' ')}（cwd=${projectRoot}，绑定 ${BIND_HOST}:${API_PORT}）`);

  // Windows 下 uv 可能是 uv.exe 或 .cmd 垫片：走 shell 让 cmd.exe 解析 PATH/PATHEXT，
  // windowsHide 避免弹出控制台窗口；args 无空格，无引号坑。其余平台直接 spawn。
  backend = spawn('uv', args, {
    cwd: projectRoot,
    env: { ...process.env },
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: isWin,
    windowsHide: true,
  });

  backend.stdout.on('data', (chunk) => process.stdout.write(`[api] ${chunk.toString()}`));
  backend.stderr.on('data', (chunk) => process.stderr.write(`[api] ${chunk.toString()}`));

  backend.on('error', (err) => {
    // ENOENT：找不到 uv。
    log('后端启动失败：', err.message);
    if (!quitting) {
      dialog.showErrorBox(
        'Novel Editorial',
        `无法启动后端（${err.message}）。\n请确认已安装 uv 且在 PATH 中。`,
      );
      app.quit();
    }
  });

  backend.on('exit', (code, signal) => {
    // 先保存退出码与信号快照：backend 随即置 null，后续 waitForReady 仍要读到。
    backendExitCode = code;
    backendExitSignal = signal;
    log(`后端进程退出 code=${code} signal=${signal}`);
    backend = null;
    if (!quitting && mainWindow) {
      // 后端意外退出时窗口页面会连接失败，这里仅记日志，由退出清理兜底。
      log('后端已退出，窗口仍打开（页面可能失去连接）');
    }
  });
}

function killBackend() {
  if (backendStopped || !backend) return;
  backendStopped = true;
  const child = backend;
  if (isWin && child.pid) {
    // taskkill /T /F 杀整棵进程树，避免残留 uvicorn 子进程。
    // taskkill 是独立进程，Electron 主进程退出后它仍会执行完杀树，异步 spawn 足够，
    // 无需 spawnSync 阻塞退出。
    try {
      const killer = spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], {
        stdio: 'ignore',
        windowsHide: true,
      });
      killer.on('error', () => {
        try {
          child.kill();
        } catch {
          /* ignore */
        }
      });
    } catch {
      try {
        child.kill();
      } catch {
        /* ignore */
      }
    }
  } else {
    try {
      child.kill();
    } catch {
      /* ignore */
    }
  }
}

function checkHealth() {
  return new Promise((resolve, reject) => {
    const req = http.get(`${BASE_URL}/health`, { timeout: 1000 }, (res) => {
      res.resume();
      if (res.statusCode === 200) {
        resolve();
      } else {
        reject(new Error(`HTTP ${res.statusCode}`));
      }
    });
    req.on('timeout', () => req.destroy(new Error('health check timeout')));
    req.on('error', reject);
  });
}

function waitForReady() {
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + READY_TIMEOUT_MS;
    const tick = () => {
      checkHealth()
        .then(() => resolve())
        .catch(() => {
          if (backend === null || backend.exitCode !== null) {
            // 后端已退出（或没起来），直接失败；退出码用退出回调里保存的快照。
            return reject(new Error(`后端提前退出（exit ${backendExitCode ?? 'signal ' + backendExitSignal}）`));
          }
          if (Date.now() >= deadline) {
            return reject(new Error(`后端就绪超时（${READY_TIMEOUT_MS / 1000}s）`));
          }
          setTimeout(tick, POLL_INTERVAL_MS);
        });
    };
    tick();
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    title: 'Novel Editorial',
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  // 新窗口（target=_blank / window.open）一律拦截，外链交给系统浏览器。
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    openExternal(url);
    return { action: 'deny' };
  });

  // 页面跳转到非同源地址时拦截，外链交给系统浏览器。
  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (!isSameOrigin(url)) {
      event.preventDefault();
      openExternal(url);
    }
  });

  // 服务端重定向逃逸到外链时同样拦截（will-navigate 不覆盖 302 重定向）。
  mainWindow.webContents.on('will-redirect', (event, url) => {
    if (!isSameOrigin(url)) {
      event.preventDefault();
      openExternal(url);
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  mainWindow.loadURL(BASE_URL);
}

function bootstrap() {
  const projectRoot = findProjectRoot();
  if (!projectRoot) {
    dialog.showErrorBox(
      'Novel Editorial',
      '找不到项目根目录（含 pyproject.toml）。\n请设置 NOVEL_APP_ROOT 指向项目根，' +
        '或把可执行文件放进项目根目录。',
    );
    app.quit();
    return;
  }
  log(`项目根：${projectRoot}，API：${BASE_URL}`);

  startBackend(projectRoot);

  waitForReady()
    .then(() => {
      log('后端就绪，开窗');
      createWindow();
      if (pendingFocus) {
        // 开窗前有 second-instance 触发过：补聚焦并复位。
        pendingFocus = false;
        if (mainWindow.isMinimized()) mainWindow.restore();
        mainWindow.focus();
      }
    })
    .catch((err) => {
      log('启动失败：', err.message);
      if (!quitting) {
        dialog.showErrorBox('Novel Editorial', `后端启动失败：${err.message}`);
      }
      app.quit();
    });
}

// —— 单实例锁：重复启动时聚焦已有窗口 ——
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    } else {
      // bootstrap 尚未开窗：记下待聚焦，开窗后再补。
      pendingFocus = true;
    }
  });

  app.whenReady().then(bootstrap);
}

// —— 退出清理：结束后端进程树，保证无残留 ——
app.on('before-quit', () => {
  quitting = true;
  killBackend();
});
app.on('will-quit', () => {
  killBackend();
});
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
