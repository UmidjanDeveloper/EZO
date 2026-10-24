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
    chat: async (message: string, id: string | null, hint: string | null = null) => {
      log.push(hint ? `chat:${message}:${id}:${hint}` : `chat:${message}:${id}`);
      return { conversationId: "11111111-1111-1111-1111-111111111111", text: "Model javobi: kalkulyatorni och", language: hint };
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
      language: "uz",
    });
    expect(log).toEqual(["app:calculator"]);
  });

  it("answers in the language the owner spoke", async () => {
    const { assistant } = setup({ apps: { ...DEFAULT_SETTINGS.apps, calculator: true } });
    expect(await assistant.handle("Открой калькулятор")).toMatchObject({ reply: "Калькулятор открыт.", language: "ru" });
    expect(await assistant.handle("Open the calculator")).toMatchObject({ reply: "Calculator is open.", language: "en" });
    // The language the server heard wins over the guess from the words.
    expect(await assistant.handle("calculator", "ru")).toMatchObject({ language: "ru" });
    const locked = setup();
    expect(await locked.assistant.handle("Open the calculator")).toMatchObject({
      reply: "This action is not allowed yet. Turn it on in EZO settings.",
      acted: false,
    });
  });

  it("chat replies keep the language the server chose", async () => {
    const { assistant, log } = setup();
    const result = await assistant.handle("Okay, thanks", "en");
    expect(result.language).toBe("en");
    expect(log[0]).toBe("chat:Okay, thanks:null:en");
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

describe("JARVIS tasks from speech", () => {
  const REFERENCE =
    "Downloads ichidagi eng oxirgi faylni och, PDF'ga aylantir, foiz ko'rsatkichlarini undan oldingi faylga o'xshatib tayyorla va Telegram'da Baxtiyorga yubor.";

  function jarvisSetup(paired: boolean, create: (text: string) => Promise<{ id: string; state: string; report: string }>) {
    const tracked: string[] = [];
    const settings: DesktopSettings = {
      ...DEFAULT_SETTINGS,
      jarvisDeviceId: paired ? "33333333-3333-4333-8333-333333333333" : null,
    };
    const client = { createJarvisTask: create, chat: async () => ({ conversationId: "x", text: "chat" }) } as unknown as EzoClient;
    const deps: AssistantDeps = {
      settings: () => settings,
      client: () => client,
      actions: {} as Actions,
      findFiles: async () => [],
      isInsideAllowed: async () => false,
      confirm: async () => true,
      captureScreen: async () => new Uint8Array(),
      saveConversation: () => undefined,
      trackTask: (id) => tracked.push(id),
    };
    return { assistant: createAssistant(deps), tracked };
  }

  it("is a governed task, not 'open a file named Downloads'", async () => {
    const { assistant, tracked } = jarvisSetup(true, async () => ({ id: "t1", state: "running", report: "" }));
    const turn = await assistant.handle(REFERENCE);
    expect(turn.intent).toBe("jarvis_task");
    expect(turn.reply).toContain("Vazifa boshlandi");
    expect(tracked).toEqual(["t1"]);
  });

  it("asks to pair first instead of pretending", async () => {
    const { assistant } = jarvisSetup(false, async () => {
      throw new Error("must not be called");
    });
    expect((await assistant.handle(REFERENCE)).reply).toContain("ulanmagan");
  });

  it("reports the server's reason when a prerequisite is missing", async () => {
    const refusal = Object.assign(new Error("“Baxtiyor” is not a linked Telegram recipient."), { code: "recipient_not_linked" });
    const { assistant, tracked } = jarvisSetup(true, async () => {
      throw refusal;
    });
    const turn = await assistant.handle(REFERENCE);
    expect(turn.reply).toContain("not a linked Telegram recipient");
    expect(turn.acted).toBe(false);
    expect(tracked).toEqual([]);
  });
});
