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

  it("lets the server recognise Uzbek, English or Russian (auto) and reports what it heard", async () => {
    const { calls, impl } = fakeFetch(() => Response.json({ text: " Привет ", language: "ru" }));
    const api = createApi("https://x", "t", impl);
    expect(await api.transcribe(new Blob(["a"]))).toEqual({ text: "Привет", language: "ru" });
    expect((calls[0]!.init.body as FormData).get("language")).toBeNull();
    await api.transcribe(new Blob(["a"]), "uz");
    expect((calls[1]!.init.body as FormData).get("language")).toBe("uz");
  });

  it("passes the heard language with a voice turn and speaks the reply in the reply's language", async () => {
    const { calls, impl } = fakeFetch(() =>
      Response.json({ conversation_id: "c1", language: "en", message: { id: "m", role: "assistant", content: "Hi", created_at: "" } }),
    );
    const api = createApi("https://x", "t", impl);
    const out = await api.chat("Okay", null, null, "voice", "en");
    expect(out.language).toBe("en");
    expect(JSON.parse(String(calls[0]!.init.body))).toMatchObject({ channel: "voice", language_hint: "en" });
    await api.chat("Salom", null, null, "text", "uz");
    expect(JSON.parse(String(calls[1]!.init.body))).not.toHaveProperty("language_hint");
    await api.speak("Hi", "en").catch(() => undefined);
    expect(JSON.parse(String(calls[2]!.init.body))).toMatchObject({ language: "en" });
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

describe("EZO Student from the phone", () => {
  it("uploads raw bytes as octet-stream with the filename, then reads the real job and summary", async () => {
    const { calls, impl } = fakeFetch(() =>
      Response.json({ id: "j1", document_id: "d1", state: "queued", error_code: null, error_message: null, text: "Xulosa [1]", citations: [{}] }),
    );
    const api = createApi("https://api.ezo.uz", "tok", impl);
    const job = await api.uploadStudent("Kitob 1.pdf", new Uint8Array([37, 80, 68, 70]));
    expect(job.state).toBe("queued");
    expect(calls[0]!.url).toBe("https://api.ezo.uz/api/student/uploads?filename=Kitob%201.pdf");
    expect(new Headers(calls[0]!.init.headers).get("Content-Type")).toBe("application/octet-stream");
    await api.studentJob("j1");
    expect(calls[1]!.url).toBe("https://api.ezo.uz/api/knowledge/document-jobs/j1");
    expect(await api.studentSummary("d1")).toEqual({ text: "Xulosa [1]", citations: 1 });
    expect(JSON.parse(String(calls[2]!.init.body))).toEqual({ kind: "summary", language: "uz" });
  });
});

describe("createApi: status, files, IELTS, JARVIS, cancellation", () => {
  it("reads the server's real capabilities and never assumes an AI provider", async () => {
    const { impl } = fakeFetch(() => Response.json({ offline_mode: true, providers: [{ name: "openai", configured: false }] }));
    expect(await createApi("https://x", "t", impl).status()).toEqual({ online: true, ai: false, voice: false, providers: [] });
  });

  it("downloads a generated file with the server's own filename", async () => {
    const { calls, impl } = fakeFetch(
      () => new Response(new Blob([new Uint8Array([80, 75, 3, 4])]), { headers: { "Content-Disposition": 'attachment; filename="Hisobot oktyabr.docx"' } }),
    );
    const file = await createApi("https://x", "t", impl).downloadArtifact("a1");
    expect(file.filename).toBe("Hisobot oktyabr.docx");
    expect(file.blob.size).toBe(4);
    expect(calls[0]!.url).toBe("https://x/api/artifacts/a1/download");
  });

  it("starts an IELTS session with a chosen cue card and sends the phone-measured speaking time", async () => {
    const { calls, impl } = fakeFetch(() => Response.json({ session_id: "s", part: 1, instruction: "", finished: false, metrics: null }));
    const api = createApi("https://x", "t", impl);
    await api.startIelts("place");
    expect(JSON.parse(String(calls[0]!.init.body))).toEqual({ cue_card: "place" });
    await api.ieltsAdvance("s", "My name is Umid.", 4.2);
    expect(calls[1]!.url).toBe("https://x/api/ielts/sessions/s/advance");
    expect(JSON.parse(String(calls[1]!.init.body))).toEqual({ answer: "My name is Umid.", speech_seconds: 4.2 });
  });

  it("approves a JARVIS step only with the server's scope hash, and cancels through the server", async () => {
    const { calls, impl } = fakeFetch(() => Response.json({ id: "t1", state: "running", steps: [] }));
    const api = createApi("https://x", "t", impl);
    await api.decideJarvisStep("t1", "s1", "a".repeat(64), true);
    expect(calls[0]!.url).toBe("https://x/api/jarvis/tasks/t1/steps/s1/decision");
    expect(JSON.parse(String(calls[0]!.init.body))).toEqual({ scope_sha256: "a".repeat(64), approve: true });
    await api.cancelJarvisTask("t1");
    expect(calls[1]!.url).toBe("https://x/api/jarvis/tasks/t1/cancel");
    await api.createJarvisTask("Downloads dagi oxirgi faylni yubor", "uz");
    expect(JSON.parse(String(calls[2]!.init.body))).toMatchObject({ language: "uz" });
    expect(JSON.parse(String(calls[2]!.init.body)).idempotency_key).toMatch(/^mobile-/);
  });

  it("reports an aborted request as cancelled, in the chosen language", async () => {
    const controller = new AbortController();
    const impl = ((_url: string, init: RequestInit) =>
      new Promise<Response>((_resolve, reject) => init.signal?.addEventListener("abort", () => reject(new DOMException("x", "AbortError"))))) as unknown as typeof fetch;
    const api = createApi("https://x", "t", impl, { lang: "en", signal: controller.signal });
    const pending = api.chat("Hi", null, null, "text").catch((e: unknown) => e);
    controller.abort();
    const error = (await pending) as ApiError;
    expect(error.code).toBe("cancelled");
    expect(error.message).toBe("Cancelled.");
    const { impl: unauthorized } = fakeFetch(() => Response.json({ error: { code: "x" } }, { status: 401 }));
    const ru = (await createApi("https://x", "bad", unauthorized, { lang: "ru" }).me().catch((e: unknown) => e)) as ApiError;
    expect(ru.message).toContain("Токен");
  });
});
