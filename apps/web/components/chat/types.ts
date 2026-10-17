import type { ChatErrorEvent, LanguageCode, MessageMetadata } from "@ezo/shared";

/** A message as shown in the chat UI (persisted or still streaming). */
export interface UiMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  agent?: string | null;
  runId?: string | null;
  metadata?: MessageMetadata;
  /** Language EZO detected for the turn (used to pick the speaking voice). */
  language?: LanguageCode;
  streaming?: boolean;
  error?: ChatErrorEvent | { code: string; message: string; hint?: string };
}
