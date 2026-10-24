/**
 * One turn of the desktop assistant: user words in, an honest reply out.
 * Registered actions run only when the matching permission is on; everything else is a
 * normal EZO conversation through the API. The reply text is never executed.
 */
import type { Actions } from "./actions";
import { UnsupportedAction } from "./actions";
import type { EzoClient } from "./api";
import type { FileHit } from "./files";
import { parseIntent, type Intent } from "./intents";
import { guessLanguage, replies, type Lang } from "./replies";
import type { DesktopSettings } from "./settings";

export interface TurnResult {
  intent: Intent["kind"];
  reply: string;
  /** True when a local action really ran (not just a reply). */
  acted: boolean;
  /** Language of `reply`, so it is read aloud with the right voice. */
  language: Lang;
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
  /** Watch a JARVIS task so its approvals and final report reach the owner. */
  trackTask?(taskId: string): void;
}

export function createAssistant(deps: AssistantDeps) {
  let lastResults: FileHit[] = [];

  function listHits(hits: FileHit[]): string {
    return hits
      .slice(0, 5)
      .map((hit, i) => `${i + 1}. ${hit.name}`)
      .join("\n");
  }

  async function openHit(hit: FileHit, lang: Lang): Promise<TurnResult> {
    const settings = deps.settings();
    const t = replies(lang);
    if (!(await deps.isInsideAllowed(hit.path, settings.allowedFolders))) {
      return { intent: "open_file", reply: t.outside, acted: false, language: lang };
    }
    await deps.actions.openFile(hit.path);
    return { intent: "open_file", reply: t.fileOpened(hit.name), acted: true, language: lang };
  }

  /** `heard`: the language the server recognised in the user's speech (null for typed text). */
  async function handle(text: string, heard: Lang | null = null): Promise<TurnResult> {
    const intent = parseIntent(text);
    const settings = deps.settings();
    const lang = heard ?? guessLanguage(text);
    const t = replies(lang);
    const say = (reply: string, acted = false): TurnResult => ({ intent: intent.kind, reply, acted, language: lang });
    try {
      switch (intent.kind) {
        case "open_app":
          if (!settings.apps[intent.app]) return say(t.needPermission);
          await deps.actions.openApp(intent.app);
          return say(t.opened(t.app(intent.app)), true);

        case "volume":
          if (!settings.allowVolume) return say(t.needPermission);
          await deps.actions.changeVolume(intent.change);
          return say(t.volume[intent.change], true);

        case "dictate":
          if (!settings.allowTyping) return say(t.needPermission);
          await deps.actions.typeText(intent.text);
          return say(t.typed, true);

        case "find_file":
        case "open_file": {
          if (settings.allowedFolders.length === 0) return say(t.addFolder);
          lastResults = await deps.findFiles(intent.query, settings.allowedFolders);
          if (lastResults.length === 0) return say(t.notFound(intent.query));
          if (intent.kind === "open_file" && lastResults.length === 1) return openHit(lastResults[0]!, lang);
          return say(t.found(lastResults.length, listHits(lastResults)));
        }

        case "open_result": {
          const hit = lastResults[intent.index];
          if (!hit) return say(t.searchFirst);
          return openHit(hit, lang);
        }

        case "explain_screen": {
          if (!settings.allowScreen) return say(t.needPermission);
          const ok = await deps.confirm(t.screenConfirm);
          if (!ok) return say(t.cancelled);
          const png = await deps.captureScreen();
          return say(await deps.client().describeImage(png, intent.question, lang), true);
        }

        case "jarvis_task": {
          if (!settings.jarvisDeviceId) return say(t.jarvisNotPaired);
          try {
            const task = await deps.client().createJarvisTask(intent.text, lang);
            deps.trackTask?.(task.id);
            return say(task.state === "failed" ? task.report : t.jarvisStarted, true);
          } catch (error) {
            // The server explains what is missing (recipient not linked, no device, …).
            if (error instanceof Error && "code" in error) return say(error.message);
            throw error;
          }
        }

        case "chat": {
          const answer = await deps.client().chat(intent.text, settings.conversationId, heard);
          deps.saveConversation(answer.conversationId);
          return { intent: intent.kind, reply: answer.text, acted: false, language: answer.language ?? lang };
        }
      }
    } catch (error) {
      if (error instanceof UnsupportedAction) return say(error.message);
      throw error;
    }
  }

  return { handle };
}
