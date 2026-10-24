// Settings window: server, token (write-only), revocable permissions and allowed folders.

type AppId = "calculator" | "notepad" | "paint" | "explorer";

interface DesktopSettings {
  apiUrl: string;
  allowedFolders: string[];
  apps: Record<AppId, boolean>;
  allowTyping: boolean;
  allowScreen: boolean;
  allowVolume: boolean;
  speakReplies: boolean;
  shortcut: string;
  conversationId: string | null;
  jarvisFolder: string | null;
  jarvisDeviceId: string | null;
}

interface SettingsBridge {
  get(): Promise<{ settings: DesktopSettings; hasToken: boolean; secureStorage: boolean; shortcuts: string[]; platform: string }>;
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
const FLAGS = ["allowVolume", "allowTyping", "allowScreen", "speakReplies"] as const;

function renderFolders(settings: DesktopSettings): void {
  const list = byId<HTMLUListElement>("folders");
  list.replaceChildren(
    ...settings.allowedFolders.map((folder) => {
      const item = document.createElement("li");
      item.textContent = folder;
      const remove = document.createElement("button");
      remove.className = "secondary";
      remove.textContent = "Olib tashlash";
      remove.addEventListener("click", async () => renderFolders(await bridge.removeFolder(folder)));
      item.append(remove);
      return item;
    }),
  );
  if (settings.allowedFolders.length === 0) {
    const empty = document.createElement("li");
    empty.textContent = "Hali papka qo‘shilmagan — fayl qidirish o‘chiq.";
    list.append(empty);
  }
}

function tokenState(hasToken: boolean, secure: boolean): void {
  byId("tokenState").textContent = !secure
    ? "Diqqat: tizimning shifrlangan saqlash joyi mavjud emas, token saqlanmaydi."
    : hasToken
      ? "Token shifrlangan holda saqlangan (qayta ko‘rsatilmaydi)."
      : "Token kiritilmagan (faqat mahalliy rejimdagi server uchun yetarli).";
}

async function renderJarvis(settings: DesktopSettings): Promise<void> {
  byId("jarvisFolder").textContent = settings.jarvisFolder ?? "Tanlanmagan — JARVIS fayl o‘qiy olmaydi.";
  const state = byId("jarvisState");
  if (!settings.jarvisDeviceId) {
    state.textContent = "Bu kompyuter ulanmagan.";
    return;
  }
  const status = await bridge.jarvisStatus();
  state.textContent =
    status.status === "paired"
      ? "Ulangan ✓ (vazifalar har safar sizdan so‘raladi)."
      : status.status === "pending"
        ? "Kutilmoqda: kodni EZO ilovasida tasdiqlang."
        : status.message ?? `Holat: ${status.status}`;
}

async function init(): Promise<void> {
  const { settings, hasToken, secureStorage, shortcuts } = await bridge.get();
  byId<HTMLInputElement>("apiUrl").value = settings.apiUrl;
  tokenState(hasToken, secureStorage);
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
      tokenState(ok, secureStorage);
    }
  });
  byId("clearToken").addEventListener("click", async () => {
    await bridge.setToken(null);
    tokenState(false, secureStorage);
  });
  byId("test").addEventListener("click", async () => {
    const out = byId("testResult");
    out.textContent = "Tekshirilmoqda…";
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
    out.textContent = "Ulanmoqda…";
    const result = await bridge.jarvisPair();
    out.textContent = result.ok ? `Kod: ${result.code} — ${result.message}` : result.message;
    void renderJarvis((await bridge.get()).settings);
  });
  byId("jarvisUnpair").addEventListener("click", async () => {
    byId("jarvisCode").textContent = "";
    void renderJarvis(await bridge.jarvisUnpair());
  });
  byId("newConversation").addEventListener("click", async () => {
    await bridge.forgetConversation();
    byId("testResult").textContent = "Keyingi gap yangi suhbatda boshlanadi.";
  });
}

void init();
