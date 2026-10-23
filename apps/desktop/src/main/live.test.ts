/**
 * Opt-in check against a REAL running EZO API (set EZO_LIVE_API=http://host:port and,
 * in token mode, EZO_LIVE_TOKEN). It drives the desktop client and the mobile client
 * against the same server: a conversation started on the desktop must be listed and
 * continued by the phone. Without EZO_LIVE_API it is skipped; it needs no AI keys.
 */
import { describe, expect, it } from "vitest";
import { createApi } from "../../../mobile/src/api";
import { createEzoClient, EzoApiError } from "./api";

const url = process.env.EZO_LIVE_API;
const token = process.env.EZO_LIVE_TOKEN ?? null;

describe.skipIf(!url)("live EZO API (desktop + mobile clients)", () => {
  it("a desktop conversation is visible on the phone and can be continued there", async () => {
    const desktop = createEzoClient(url!, token);
    const phone = createApi(url!, token);
    const first = await desktop.chat("Salom EZO, bu desktopdan birinchi xabar.", null);
    expect(first.text.length).toBeGreaterThan(0);

    const listed = await phone.conversations();
    expect(listed.map((c) => c.id)).toContain(first.conversationId);

    const continued = await phone.chat("Telefondan davom etyapman.", first.conversationId, null, "text");
    expect(continued.conversationId).toBe(first.conversationId);

    const messages = await phone.messages(first.conversationId);
    expect(messages.map((m) => m.content)).toEqual(
      expect.arrayContaining(["Salom EZO, bu desktopdan birinchi xabar.", "Telefondan davom etyapman."]),
    );
  });

  it("voice and vision report missing providers honestly instead of inventing output", async () => {
    const desktop = createEzoClient(url!, token);
    const status = await fetch(`${url}/api/voice/status`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    }).then((r) => r.json() as Promise<{ speech_to_text: string[] }>);
    if (status.speech_to_text.length === 0) {
      const error = await desktop.transcribe(new Uint8Array([0x1a, 0x45, 0xdf, 0xa3, 0, 0, 0, 0]), "audio/webm").catch((e: unknown) => e);
      expect(error).toBeInstanceOf(EzoApiError);
      expect((error as EzoApiError).code).toBe("voice_not_configured");
    }
    const png = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 0]);
    const vision = await desktop.describeImage(png, "Bu nima?").catch((e: unknown) => e);
    if (vision instanceof EzoApiError) expect(["vision_not_configured", "vision_failed"]).toContain(vision.code);
  });
});
