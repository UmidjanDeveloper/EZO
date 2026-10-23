import { describe, expect, it } from "vitest";
import { ApiError, createApi } from "./api";

function fakeFetch(respond: () => Response) {
  const calls: { url: string; init: RequestInit }[] = [];
  const impl = (async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return respond();
  }) as unknown as typeof fetch;
  return { calls, impl };
}

describe("createApi", () => {
  it("continues the same conversation (the one the desktop started) with the owner token", async () => {
    const { calls, impl } = fakeFetch(() =>
      Response.json({ conversation_id: "c1", message: { id: "m", role: "assistant", content: "Salom", created_at: "" } }),
    );
    const out = await createApi("https://api.ezo.uz/", "tok", impl).chat("Davom etamiz", "c1", null, "voice");
    expect(out.conversationId).toBe("c1");
    expect(calls[0]!.url).toBe("https://api.ezo.uz/api/chat");
    expect(new Headers(calls[0]!.init.headers).get("Authorization")).toBe("Bearer tok");
    expect(JSON.parse(String(calls[0]!.init.body))).toMatchObject({ conversation_id: "c1", channel: "voice" });
  });

  it("sends audio for Uzbek transcription", async () => {
    const { calls, impl } = fakeFetch(() => Response.json({ text: " salom " }));
    expect(await createApi("https://x", "t", impl).transcribe(new Blob(["a"]))).toBe("salom");
    expect((calls[0]!.init.body as FormData).get("language")).toBe("uz");
  });

  it("explains missing server features in Uzbek", async () => {
    const { impl } = fakeFetch(() => Response.json({ error: { code: "voice_not_configured" } }, { status: 503 }));
    await expect(createApi("https://x", "t", impl).speak("salom")).rejects.toMatchObject({
      code: "voice_not_configured",
    });
  });

  it("reports network failure (for example CORS) instead of failing silently", async () => {
    const impl = (async () => {
      throw new TypeError("Failed to fetch");
    }) as unknown as typeof fetch;
    const error = await createApi("https://x", "t", impl).me().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toContain("CORS");
  });
});
