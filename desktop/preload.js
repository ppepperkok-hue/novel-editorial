const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("desktopApi", {
  isDesktop: true,
  minimize: () => ipcRenderer.send("win:minimize"),
  maximize: () => ipcRenderer.send("win:maximize"),
  close: () => ipcRenderer.send("win:close"),
  isMaximized: () => ipcRenderer.invoke("win:is-maximized"),
  setAutoLaunch: (enabled) => ipcRenderer.invoke("app:set-auto-launch", enabled),
  getAutoLaunch: () => ipcRenderer.invoke("app:get-auto-launch"),
  closeToTray: () => ipcRenderer.send("app:close-to-tray"),
  quit: () => ipcRenderer.send("app:quit"),
});
