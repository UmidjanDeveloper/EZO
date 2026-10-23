// Settings bridge: the token can be written or cleared, but never read back.
import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("ezoSettings", {
  get: () => ipcRenderer.invoke("settings:get"),
  save: (patch: unknown) => ipcRenderer.invoke("settings:save", patch),
  setToken: (token: string | null) => ipcRenderer.invoke("settings:token", token),
  addFolder: () => ipcRenderer.invoke("settings:add-folder"),
  removeFolder: (folder: string) => ipcRenderer.invoke("settings:remove-folder", folder),
  forgetConversation: () => ipcRenderer.invoke("settings:forget-conversation"),
  test: () => ipcRenderer.invoke("settings:test"),
});
