// Settings window: server, token (write-only), language, revocable permissions and allowed folders.

type AppId = "calculator" | "notepad" | "paint" | "explorer";

interface DesktopSettings {
  apiUrl: string;
  language: "uz" | "en" | "ru";
  allowedFolders: string[];
  apps: Record<AppId, boolean>;
  allowTyping: boolean;
  allowScreen: boolean;
  allowVolume: boolean;
  speakReplies: boolean;
  allowMicrophone: boolean;
  allowCamera: boolean;
  lowPower: boolean;
  onboarded: boolean;
  shortcut: string;
  conversationId: string | null;
  jarvisFolder: string | null;
  jarvisDeviceId: string | null;
}

type SettingsStrings = Record<string, string>;

interface SettingsBridge {
  get(): Promise<{
    settings: DesktopSettings;
    hasToken: boolean;
    secureStorage: boolean;
    shortcuts: string[];
    platform: string;
    strings: SettingsStrings;
    languages: { code: DesktopSettings["language"]; label: string }[];
  }>;
  save(patch: Partial<DesktopSettings>): Promise<DesktopSettings>;
  setToken(token: string | null): Promise<boolean>;
  addFolder(): Promise<DesktopSettings>;
  removeFolder(folder: string): Promise<DesktopSettings>;
  forgetConversation(): Promise<DesktopSettings>;
  test(): Promise<{ ok: boolean; message: string }>;
  jarvisChooseFolder(): Promise<DesktopSettings>;
  jarvisClearFolder(): Promise<DesktopSettings>;
  jarvisPair(): Promise<{ ok: boolean; code?: string; message: string }>;
  jarvisUnpair(): Promise<DesktopSettings>;
  jarvisStatus(): Promise<{ paired: boolean; status: string; message?: string }>;
}

const bridge = (window as unknown as { ezoSettings: SettingsBridge }).ezoSettings;
const byId = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const FLAGS = ["allowVolume", "allowTyping", "allowScreen", "speakReplies", "allowMicrophone", "allowCamera", "lowPower"] as const;
let t: SettingsStrings = {};
let secure = true;
let pairingPoll: number | undefined;

const fmt = (key: string, values: Record<string, string> = {}) =>
  (t[key] ?? key).replace(/\{(\w+)\}/g, (match, name: string) => values[name] ?? match);

function applyStrings(): void {
  for (const node of document.querySelectorAll<HTMLElement>("[data-i18n]")) node.textContent = fmt(node.dataset.i18n!);
}

function renderFolders(settings: DesktopSettings): void {
  const list = byId<HTMLUListElement>("folders");
  list.replaceChildren(
    ...settings.allowedFolders.map((folder) => {
      const item = document.createElement("li");
      item.textContent = folder;
      const remove = document.createElement("button");
      remove.className = "secondary";
      remove.textContent = fmt("removeFolder");
      remove.addEventListener("click", async () => renderFolders(await bridge.removeFolder(folder)));
      item.append(remove);
      return item;
    }),
  );
  if (settings.allowedFolders.length === 0) {
    const empty = document.createElement("li");
    empty.textContent = fmt("noFolders");
    list.append(empty);
  }
}

function tokenState(hasToken: boolean): void {
  byId("tokenState").textContent = !secure ? fmt("noSecureStorage") : hasToken ? fmt("tokenSaved") : fmt("tokenMissing");
}

async function renderJarvis(settings: DesktopSettings): Promise<void> {
  byId("jarvisFolder").textContent = settings.jarvisFolder ?? fmt("jarvisFolderNone");
  const state = byId("jarvisState");
  window.clearInterval(pairingPoll);
  if (!settings.jarvisDeviceId) {
    state.textContent = fmt("jarvisNotPaired");
    return;
  }
  const status = await bridge.jarvisStatus();
  state.textContent =
    status.status === "paired"
      ? fmt("jarvisPaired")
      : status.status === "pending"
        ? fmt("jarvisPending")
        : (status.message ?? fmt("jarvisStatus", { status: status.status }));
  // While the owner confirms the code in the web app, the state refreshes by itself.
  if (status.status === "pending") pairingPoll = window.setInterval(() => void renderJarvis(settings), 5000);
}

async function init(): Promise<void> {
  const { settings, hasToken, secureStorage, shortcuts, strings, languages } = await bridge.get();
  t = strings;
  secure = secureStorage;
  document.documentElement.lang = settings.language;
  applyStrings();
  // First run: a short welcome at the top, until the owner closes it.
  const welcome = byId("welcome");
  welcome.hidden = settings.onboarded;
  byId("welcomeStep3").textContent = fmt("welcomeStep3", { shortcut: settings.shortcut.replace("Control", "Ctrl") });
  byId("welcomeDone").addEventListener("click", async () => {
    await bridge.save({ onboarded: true });
    welcome.hidden = true;
  });
  byId<HTMLInputElement>("apiUrl").value = settings.apiUrl;
  tokenState(hasToken);
  const language = byId<HTMLSelectElement>("language");
  language.replaceChildren(
    ...languages.map((l) => {
      const option = document.createElement("option");
      option.value = l.code;
      option.textContent = l.label;
      option.selected = l.code === settings.language;
      return option;
    }),
  );
  language.addEventListener("change", async () => {
    await bridge.save({ language: language.value as DesktopSettings["language"] });
    t = (await bridge.get()).strings;
    document.documentElement.lang = language.value;
    applyStrings();
    renderFolders((await bridge.get()).settings);
    tokenState((await bridge.get()).hasToken);
    void renderJarvis((await bridge.get()).settings);
  });
  for (const box of document.querySelectorAll<HTMLInputElement>("input[data-app]")) {
    const app = box.dataset.app as AppId;
    box.checked = settings.apps[app];
    box.addEventListener("change", async () => {
      const current = (await bridge.get()).settings;
      await bridge.save({ apps: { ...current.apps, [app]: box.checked } });
    });
  }
  for (const flag of FLAGS) {
    const box = byId<HTMLInputElement>(flag);
    box.checked = settings[flag];
    box.addEventListener("change", () => void bridge.save({ [flag]: box.checked }));
  }
  const select = byId<HTMLSelectElement>("shortcut");
  select.replaceChildren(
    ...shortcuts.map((s) => {
      const option = document.createElement("option");
      option.value = s;
      option.textContent = s.replace("Control", "Ctrl");
      option.selected = s === settings.shortcut;
      return option;
    }),
  );
  select.addEventListener("change", () => void bridge.save({ shortcut: select.value }));
  renderFolders(settings);

  byId("saveServer").addEventListener("click", async () => {
    const saved = await bridge.save({ apiUrl: byId<HTMLInputElement>("apiUrl").value.trim() });
    byId<HTMLInputElement>("apiUrl").value = saved.apiUrl;
    const token = byId<HTMLInputElement>("token").value.trim();
    if (token) {
      const ok = await bridge.setToken(token);
      byId<HTMLInputElement>("token").value = "";
      tokenState(ok);
    }
    const out = byId("testResult");
    out.textContent = fmt("saved");
    out.className = "ok";
  });
  byId("clearToken").addEventListener("click", async () => {
    await bridge.setToken(null);
    tokenState(false);
  });
  byId("test").addEventListener("click", async () => {
    const out = byId("testResult");
    out.textContent = fmt("testing");
    out.className = "";
    const result = await bridge.test();
    out.textContent = result.message;
    out.className = result.ok ? "ok" : "bad";
  });
  byId("addFolder").addEventListener("click", async () => renderFolders(await bridge.addFolder()));
  void renderJarvis(settings);
  byId("jarvisChoose").addEventListener("click", async () => void renderJarvis(await bridge.jarvisChooseFolder()));
  byId("jarvisClear").addEventListener("click", async () => void renderJarvis(await bridge.jarvisClearFolder()));
  byId("jarvisPair").addEventListener("click", async () => {
    const out = byId("jarvisCode");
    out.textContent = fmt("pairing");
    const result = await bridge.jarvisPair();
    out.textContent = result.ok ? fmt("code", { code: result.code ?? "", message: result.message }) : result.message;
    void renderJarvis((await bridge.get()).settings);
  });
  byId("jarvisUnpair").addEventListener("click", async () => {
    byId("jarvisCode").textContent = "";
    void renderJarvis(await bridge.jarvisUnpair());
  });
  byId("newConversation").addEventListener("click", async () => {
    await bridge.forgetConversation();
    byId("testResult").textContent = fmt("newConversationDone");
    byId("testResult").className = "ok";
  });
}

void init();
