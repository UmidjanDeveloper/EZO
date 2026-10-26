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
      Response.json({ conversation_id: "c-1", language: "uz", message: { content: "Salom!" } }),
    );
    const reply = await createEzoClient("https://api.example.com/", "secret-token", fetchImpl).chat("Salom", "c-0");
    expect(reply).toEqual({ conversationId: "c-1", text: "Salom!", language: "uz" });
    expect(calls[0]!.url).toBe("https://api.example.com/api/chat");
    expect(new Headers(calls[0]!.init.headers).get("Authorization")).toBe("Bearer secret-token");
    expect(JSON.parse(String(calls[0]!.init.body))).toEqual({
      message: "Salom",
      conversation_id: "c-0",
      channel: "voice",
    });
  });

  it("uploads audio as multipart and lets the server tell which of the three languages it heard", async () => {
    const { calls, fetchImpl } = recorder(() => Response.json({ text: " Открой калькулятор ", language: "ru" }));
    const heard = await createEzoClient("http://localhost:8000", null, fetchImpl).transcribe(
      new Uint8Array([1, 2, 3]),
      "audio/webm",
    );
    expect(heard).toEqual({ text: "Открой калькулятор", language: "ru" });
    const form = calls[0]!.init.body as FormData;
    expect(form.get("language")).toBeNull(); // auto: no language forced on the recogniser
    expect((form.get("audio") as Blob).size).toBe(3);
    expect(new Headers(calls[0]!.init.headers).has("Authorization")).toBe(false);
  });

  it("passes the heard language with the turn and asks for speech in the reply's language", async () => {
    const { calls, fetchImpl } = recorder(() => Response.json({ conversation_id: "c", language: "en", message: { content: "Hi" } }));
    const client = createEzoClient("http://x", "t", fetchImpl);
    await client.chat("Okay", null, "en");
    expect(JSON.parse(String(calls[0]!.init.body))).toMatchObject({ language_hint: "en" });
    await client.speak("Hi", "en").catch(() => undefined);
    expect(JSON.parse(String(calls[1]!.init.body))).toMatchObject({ language: "en" });
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

describe("createEzoClient: status, history, tasks and cancellation", () => {
  it("reads whether the server really has an AI provider and voice", async () => {
    const { fetchImpl } = recorder(() =>
      Response.json({
        offline_mode: false,
        version: "0.1.0",
        providers: [
          { name: "openai", configured: true, capabilities: ["chat", "speech_to_text"] },
          { name: "gemini", configured: false, capabilities: ["chat"] },
        ],
      }),
    );
    expect(await createEzoClient("http://x", "t", fetchImpl).status()).toEqual({ ai: true, voice: true, providers: ["openai"], version: "0.1.0" });
    const offline = recorder(() => Response.json({ offline_mode: true, providers: [] }));
    expect((await createEzoClient("http://x", "t", offline.fetchImpl).status()).ai).toBe(false);
  });

  it("lists the conversation's messages and recent conversations from the server", async () => {
    const { calls, fetchImpl } = recorder((url) =>
      url.includes("/messages")
        ? Response.json([{ role: "user", content: "Salom", created_at: "2026-10-26T00:00:00Z" }])
        : Response.json([{ id: "c1", title: "Salom", updated_at: "2026-10-26T00:00:00Z" }]),
    );
    const client = createEzoClient("http://x", "t", fetchImpl);
    expect((await client.messages("c1")).map((m) => m.content)).toEqual(["Salom"]);
    expect((await client.conversations()).map((c) => c.id)).toEqual(["c1"]);
    expect(calls[0]!.url).toBe("http://x/api/conversations/c1/messages?limit=12");
    expect(calls[1]!.url).toBe("http://x/api/conversations?limit=20");
  });

  it("cancels a JARVIS task through the server, never locally", async () => {
    const { calls, fetchImpl } = recorder(() => Response.json({ id: "t1", state: "cancelled", report: "", steps: [] }));
    expect((await createEzoClient("http://x", "t", fetchImpl).cancelJarvisTask("t1")).state).toBe("cancelled");
    expect(calls[0]!.url).toBe("http://x/api/jarvis/tasks/t1/cancel");
    expect(calls[0]!.init.method).toBe("POST");
  });

  it("an aborted request is reported as cancelled, not as a network failure, in the owner's language", async () => {
    const controller = new AbortController();
    const fetchImpl = ((_url: string, init: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
      })) as unknown as typeof fetch;
    const client = createEzoClient("http://x", "t", fetchImpl, { lang: "en", signal: controller.signal });
    const pending = client.chat("Hello", null).catch((e: unknown) => e);
    controller.abort();
    const error = (await pending) as EzoApiError;
    expect(error.code).toBe("cancelled");
    expect(error.message).toBe("The request was cancelled.");
  });

  it("speaks the owner's language in error messages", async () => {
    const { fetchImpl } = recorder(() => Response.json({ error: { code: "x" } }, { status: 401 }));
    const error = (await createEzoClient("http://x", "bad", fetchImpl, { lang: "ru" }).me().catch((e: unknown) => e)) as EzoApiError;
    expect(error.message).toContain("Токен");
  });
});
