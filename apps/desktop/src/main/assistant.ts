/**
 * One turn of the desktop assistant: user words in, an honest reply out.
 * Registered actions run only when the matching permission is on; everything else is a
 * normal EZO conversation through the API. The reply text is never executed.
 */
import type { Actions } from "./actions";
import { APP_NAMES_UZ, UnsupportedAction } from "./actions";
import type { EzoClient } from "./api";
import type { FileHit } from "./files";
import { parseIntent, type Intent } from "./intents";
import type { DesktopSettings } from "./settings";

export interface TurnResult {
  intent: Intent["kind"];
  reply: string;
  /** True when a local action really ran (not just a reply). */
  acted: boolean;
}

export interface AssistantDeps {
  settings(): DesktopSettings;
  client(): EzoClient;
  actions: Actions;
  findFiles(query: string, roots: readonly string[]): Promise<FileHit[]>;
  isInsideAllowed(file: string, roots: readonly string[]): Promise<boolean>;
  /** Asks the owner right now; resolves false if they decline. */
  confirm(message: string): Promise<boolean>;
  captureScreen(): Promise<Uint8Array>;
  saveConversation(id: string): void;
}

const NEED_PERMISSION = "Bu amal uchun ruxsat berilmagan. EZO sozlamalarida yoqing.";

export function createAssistant(deps: AssistantDeps) {
  let lastResults: FileHit[] = [];

  function listHits(hits: FileHit[]): string {
    return hits
      .slice(0, 5)
      .map((hit, i) => `${i + 1}. ${hit.name}`)
      .join("\n");
  }

  async function openHit(hit: FileHit): Promise<TurnResult> {
    const settings = deps.settings();
    if (!(await deps.isInsideAllowed(hit.path, settings.allowedFolders))) {
      return { intent: "open_file", reply: "Bu fayl ruxsat berilgan papkalardan tashqarida.", acted: false };
    }
    await deps.actions.openFile(hit.path);
    return { intent: "open_file", reply: `“${hit.name}” ochildi.`, acted: true };
  }

  async function handle(text: string): Promise<TurnResult> {
    const intent = parseIntent(text);
    const settings = deps.settings();
    try {
      switch (intent.kind) {
        case "open_app":
          if (!settings.apps[intent.app]) return { intent: intent.kind, reply: NEED_PERMISSION, acted: false };
          await deps.actions.openApp(intent.app);
          return { intent: intent.kind, reply: `${APP_NAMES_UZ[intent.app]} ochildi.`, acted: true };

        case "volume":
          if (!settings.allowVolume) return { intent: intent.kind, reply: NEED_PERMISSION, acted: false };
          await deps.actions.changeVolume(intent.change);
          return {
            intent: intent.kind,
            reply: { up: "Ovoz balandlatildi.", down: "Ovoz pasaytirildi.", mute: "Ovoz o‘chirildi/yoqildi." }[intent.change],
            acted: true,
          };

        case "dictate":
          if (!settings.allowTyping) return { intent: intent.kind, reply: NEED_PERMISSION, acted: false };
          await deps.actions.typeText(intent.text);
          return { intent: intent.kind, reply: "Matn faol oynaga yozildi.", acted: true };

        case "find_file":
        case "open_file": {
          if (settings.allowedFolders.length === 0) {
            return { intent: intent.kind, reply: "Avval sozlamalarda qidirish mumkin bo‘lgan papkani qo‘shing.", acted: false };
          }
          lastResults = await deps.findFiles(intent.query, settings.allowedFolders);
          if (lastResults.length === 0) {
            return { intent: intent.kind, reply: `“${intent.query}” nomli fayl ruxsat berilgan papkalarda topilmadi.`, acted: false };
          }
          if (intent.kind === "open_file" && lastResults.length === 1) return openHit(lastResults[0]!);
          return {
            intent: intent.kind,
            reply: `${lastResults.length} ta fayl topildi:\n${listHits(lastResults)}\nOchish uchun “birinchisini och” deng.`,
            acted: false,
          };
        }

        case "open_result": {
          const hit = lastResults[intent.index];
          if (!hit) return { intent: intent.kind, reply: "Avval faylni qidiring.", acted: false };
          return openHit(hit);
        }

        case "explain_screen": {
          if (!settings.allowScreen) return { intent: intent.kind, reply: NEED_PERMISSION, acted: false };
          const ok = await deps.confirm("EZO hozir ekraningiz rasmini olib, tahlil uchun EZO serveriga yuboradi. Davom etilsinmi?");
          if (!ok) return { intent: intent.kind, reply: "Bekor qilindi. Ekran rasmi olinmadi.", acted: false };
          const png = await deps.captureScreen();
          const reply = await deps.client().describeImage(png, intent.question);
          return { intent: intent.kind, reply, acted: true };
        }

        case "chat": {
          const answer = await deps.client().chat(intent.text, settings.conversationId);
          deps.saveConversation(answer.conversationId);
          return { intent: intent.kind, reply: answer.text, acted: false };
        }
      }
    } catch (error) {
      if (error instanceof UnsupportedAction) return { intent: intent.kind, reply: error.message, acted: false };
      throw error;
    }
  }

  return { handle };
}
