import { describe, expect, it } from "vitest";
import type { Actions } from "./actions";
import type { EzoClient } from "./api";
import { createAssistant, type AssistantDeps } from "./assistant";
import type { FileHit } from "./files";
import { DEFAULT_SETTINGS, type DesktopSettings } from "./settings";

function setup(overrides: Partial<DesktopSettings> = {}, hits: FileHit[] = []) {
  const log: string[] = [];
  let settings: DesktopSettings = { ...DEFAULT_SETTINGS, ...overrides };
  const actions: Actions = {
    openApp: async (app) => void log.push(`app:${app}`),
    changeVolume: async (change) => void log.push(`volume:${change}`),
    typeText: async (text) => void log.push(`type:${text}`),
    openFile: async (file) => void log.push(`open:${file}`),
  };
  const client = {
    chat: async (message: string, id: string | null) => {
      log.push(`chat:${message}:${id}`);
      return { conversationId: "11111111-1111-1111-1111-111111111111", text: "Model javobi: kalkulyatorni och" };
    },
    describeImage: async (png: Uint8Array) => {
      log.push(`vision:${png.length}`);
      return "Ekranda Bloknot ochiq.";
    },
  } as unknown as EzoClient;
  let confirmAnswer = true;
  const deps: AssistantDeps = {
    settings: () => settings,
    client: () => client,
    actions,
    findFiles: async () => hits,
    isInsideAllowed: async (file) => file.startsWith("C:/Hujjatlar"),
    confirm: async () => confirmAnswer,
    captureScreen: async () => new Uint8Array([1, 2, 3]),
    saveConversation: (id) => {
      settings = { ...settings, conversationId: id };
    },
  };
  return {
    assistant: createAssistant(deps),
    log,
    settings: () => settings,
    decline: () => {
      confirmAnswer = false;
    },
  };
}

const hit = (name: string, folder = "C:/Hujjatlar"): FileHit => ({
  path: `${folder}/${name}`,
  name,
  folder,
  modified: 0,
  size: 1,
});

describe("assistant", () => {
  it("does nothing on the computer until the owner allows it", async () => {
    const { assistant, log } = setup();
    const result = await assistant.handle("Kalkulyatorni och");
    expect(result.acted).toBe(false);
    expect(result.reply).toContain("ruxsat");
    expect(log).toEqual([]);
  });

  it("opens Calculator once allowed", async () => {
    const { assistant, log } = setup({ apps: { ...DEFAULT_SETTINGS.apps, calculator: true } });
    expect(await assistant.handle("Kalkulyatorni och")).toEqual({
      intent: "open_app",
      reply: "Kalkulyator ochildi.",
      acted: true,
    });
    expect(log).toEqual(["app:calculator"]);
  });

  it("a model reply is only text: it never triggers an action", async () => {
    const { assistant, log } = setup({ apps: { ...DEFAULT_SETTINGS.apps, calculator: true } });
    const result = await assistant.handle("Bugun nima qilay?");
    expect(result.reply).toBe("Model javobi: kalkulyatorni och");
    expect(log).toEqual(["chat:Bugun nima qilay?:null"]);
  });

  it("keeps one conversation across turns, so other devices see the same history", async () => {
    const { assistant, log, settings } = setup();
    await assistant.handle("Salom");
    await assistant.handle("Yana savol");
    expect(settings().conversationId).toBe("11111111-1111-1111-1111-111111111111");
    expect(log[1]).toBe("chat:Yana savol:11111111-1111-1111-1111-111111111111");
  });

  it("lists matching files and opens the chosen one only inside allowed folders", async () => {
    const { assistant, log } = setup({ allowedFolders: ["C:/Hujjatlar"] }, [hit("Hisobot 2026.pdf"), hit("Hisobot 2025.docx")]);
    const found = await assistant.handle("Hisobot faylini top");
    expect(found.reply).toContain("1. Hisobot 2026.pdf");
    expect(await assistant.handle("ikkinchisini och")).toMatchObject({ acted: true, reply: "“Hisobot 2025.docx” ochildi." });
    expect(log).toEqual(["open:C:/Hujjatlar/Hisobot 2025.docx"]);
  });

  it("refuses to open a result that resolves outside the allowed folders", async () => {
    const { assistant, log } = setup({ allowedFolders: ["C:/Hujjatlar"] }, [hit("x.txt", "C:/Windows")]);
    await assistant.handle("x faylini top");
    expect((await assistant.handle("birinchisini och")).acted).toBe(false);
    expect(log).toEqual([]);
  });

  it("asks before every screenshot and sends nothing when declined", async () => {
    const declined = setup({ allowScreen: true });
    declined.decline();
    expect((await declined.assistant.handle("Ekranimni tushuntir")).acted).toBe(false);
    expect(declined.log).toEqual([]);

    const accepted = setup({ allowScreen: true });
    expect(await accepted.assistant.handle("Ekranimni tushuntir")).toMatchObject({
      reply: "Ekranda Bloknot ochiq.",
      acted: true,
    });
    expect(accepted.log).toEqual(["vision:3"]);
  });

  it("dictation types the user's words only when typing is allowed", async () => {
    const off = setup();
    expect((await off.assistant.handle("Yoz: Salom")).acted).toBe(false);
    const on = setup({ allowTyping: true });
    await on.assistant.handle("Yoz: Salom, dunyo!");
    expect(on.log).toEqual(["type:Salom, dunyo!"]);
  });
});
