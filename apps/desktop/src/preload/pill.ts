// Narrow bridge for the pill: no Node, no token, no file system.
import { contextBridge, ipcRenderer } from "electron";

const on = (channel: string) => (callback: (payload: unknown) => void) => {
  ipcRenderer.on(channel, (_event, payload: unknown) => callback(payload));
};

contextBridge.exposeInMainWorld("ezo", {
  init: () => ipcRenderer.invoke("pill:init"),
  sendAudio: (audio: ArrayBuffer, mimeType: string) => ipcRenderer.invoke("turn:audio", audio, mimeType),
  sendText: (text: string) => ipcRenderer.invoke("turn:text", text),
  cancelTurn: () => ipcRenderer.send("turn:cancel"),
  openSettings: () => ipcRenderer.send("settings:open"),
  setFocusable: (focusable: boolean) => ipcRenderer.send("pill:focusable", focusable),
  setHeight: (height: number) => ipcRenderer.send("pill:height", height),
  refreshStatus: () => ipcRenderer.invoke("status:refresh"),
  recentHistory: () => ipcRenderer.invoke("history:recent"),
  conversations: () => ipcRenderer.invoke("history:conversations"),
  switchConversation: (id: string | null) => ipcRenderer.invoke("history:switch", id),
  tasks: () => ipcRenderer.invoke("jarvis:tasks"),
  cancelTask: (id: string) => ipcRenderer.invoke("jarvis:cancel-task", id),
  onToggle: (callback: () => void) => ipcRenderer.on("shortcut:toggle", () => callback()),
  onNotice: on("notice"),
  onError: on("error"),
  onStage: on("stage"),
  onStatus: on("status"),
  onTasks: on("tasks"),
  onInit: on("init"),
});
