import { describe, expect, it } from "vitest";
import { createEzoClient, EzoApiError } from "./api";

function recorder(respond: (url: string, init: RequestInit) => Response) {
  const calls: { url: string; init: RequestInit }[] = [];
  const fetchImpl = (async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return respond(url, init);
  }) as unknown as typeof fetch;
  return { calls, fetchImpl };
}

describe("createEzoClient", () => {
  it("sends the bearer token and the conversation id to /api/chat", async () => {
    const { calls, fetchImpl } = recorder(() =>
      Response.json({ conversation_id: "c-1", message: { content: "Salom!" } }),
    );
    const reply = await createEzoClient("https://api.example.com/", "secret-token", fetchImpl).chat("Salom", "c-0");
    expect(reply).toEqual({ conversationId: "c-1", text: "Salom!" });
    expect(calls[0]!.url).toBe("https://api.example.com/api/chat");
    expect(new Headers(calls[0]!.init.headers).get("Authorization")).toBe("Bearer secret-token");
    expect(JSON.parse(String(calls[0]!.init.body))).toEqual({
      message: "Salom",
      conversation_id: "c-0",
      channel: "voice",
    });
  });

  it("uploads audio as multipart with the Uzbek language hint", async () => {
    const { calls, fetchImpl } = recorder(() => Response.json({ text: " Kalkulyatorni och " }));
    const text = await createEzoClient("http://localhost:8000", null, fetchImpl).transcribe(
      new Uint8Array([1, 2, 3]),
      "audio/webm",
    );
    expect(text).toBe("Kalkulyatorni och");
    const form = calls[0]!.init.body as FormData;
    expect(form.get("language")).toBe("uz");
    expect((form.get("audio") as Blob).size).toBe(3);
    expect(new Headers(calls[0]!.init.headers).has("Authorization")).toBe(false);
  });

  it("turns API errors into honest Uzbek messages", async () => {
    const { fetchImpl } = recorder(() =>
      Response.json({ error: { code: "voice_not_configured", message: "No server speech-to-text" } }, { status: 503 }),
    );
    const error = await createEzoClient("http://x", "t", fetchImpl)
      .transcribe(new Uint8Array([1]), "audio/webm")
      .catch((e: unknown) => e);
    expect(error).toBeInstanceOf(EzoApiError);
    expect((error as EzoApiError).code).toBe("voice_not_configured");
    expect((error as EzoApiError).message).toContain("sozlanmagan");
  });

  it("reports a network failure instead of inventing an answer", async () => {
    const fetchImpl = (async () => {
      throw new TypeError("fetch failed");
    }) as unknown as typeof fetch;
    await expect(createEzoClient("http://x", "t", fetchImpl).health()).rejects.toMatchObject({ code: "network" });
  });

  it("maps 401 to a token hint", async () => {
    const { fetchImpl } = recorder(() => Response.json({ error: { code: "x" } }, { status: 401 }));
    await expect(createEzoClient("http://x", "bad", fetchImpl).me()).rejects.toMatchObject({ code: "unauthorized" });
  });
});
