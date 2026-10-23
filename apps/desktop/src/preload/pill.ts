// Narrow bridge for the pill: no Node, no token, no file system.
import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("ezo", {
  sendAudio: (audio: ArrayBuffer, mimeType: string) => ipcRenderer.invoke("turn:audio", audio, mimeType),
  sendText: (text: string) => ipcRenderer.invoke("turn:text", text),
  openSettings: () => ipcRenderer.send("settings:open"),
  setFocusable: (focusable: boolean) => ipcRenderer.send("pill:focusable", focusable),
  setHeight: (height: number) => ipcRenderer.send("pill:height", height),
  onToggle: (callback: () => void) => ipcRenderer.on("shortcut:toggle", () => callback()),
  onNotice: (callback: (text: string) => void) => ipcRenderer.on("notice", (_event, text: string) => callback(String(text))),
});
