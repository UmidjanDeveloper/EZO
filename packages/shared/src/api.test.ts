import { describe, expect, it } from "vitest";
import { ApiError, createApiClient } from "./api";

function streamResponse(chunks: string[]): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder();
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(body, { headers: { "Content-Type": "text/event-stream" } });
}

describe("createApiClient", () => {
  it("sends the bearer token and parses JSON", async () => {
    let seen: Headers | undefined;
    const client = createApiClient({
      baseUrl: "http://api/",
      getToken: () => "tok",
      fetchImpl: async (_url, init) => {
        seen = new Headers(init?.headers);
        return Response.json({ status: "ok", database: "ok", version: "0.1.0" });
      },
    });
    expect((await client.health()).status).toBe("ok");
    expect(seen?.get("Authorization")).toBe("Bearer tok");
  });

  it("uploads files as multipart form data, not JSON", async () => {
    let seenHeaders: Headers | undefined;
    let seenBody: unknown;
    const client = createApiClient({
      baseUrl: "http://api",
      fetchImpl: async (_url, init) => {
        seenHeaders = new Headers(init?.headers);
        seenBody = init?.body;
        return Response.json({ document: { id: "d1" }, duplicate: false, new_revision: false }, { status: 201 });
      },
    });
    const result = await client.uploadDocument(new Blob(["salom"]), "a.txt", "p1");
    expect(result.document.id).toBe("d1");
    expect(seenHeaders?.get("Content-Type")).toBeNull(); // the browser adds the multipart boundary
    expect(seenBody).toBeInstanceOf(FormData);
    expect((seenBody as FormData).get("project_id")).toBe("p1");
    expect(((seenBody as FormData).get("file") as File).name).toBe("a.txt");
  });

  it("downloads artifacts with their real (UTF-8) filename", async () => {
    const client = createApiClient({
      baseUrl: "http://api",
      fetchImpl: async () =>
        new Response("salom", {
          headers: {
            "Content-Disposition": `attachment; filename="Hisobot.md"; filename*=UTF-8''${encodeURIComponent("Hisobot o‘zbekcha.md")}`,
          },
        }),
    });
    const { blob, filename } = await client.downloadArtifact("a1", 2);
    expect(filename).toBe("Hisobot o‘zbekcha.md");
    expect(await blob.text()).toBe("salom");
  });

  it("turns API errors into ApiError with code and message", async () => {
    const client = createApiClient({
      baseUrl: "http://api",
      fetchImpl: async () =>
        Response.json({ error: { code: "http_404", message: "Project not found." } }, { status: 404 }),
    });
    await expect(client.getProject("x")).rejects.toMatchObject({
      status: 404,
      message: "Project not found.",
    });
  });

  it("reports network failures clearly", async () => {
    const client = createApiClient({
      baseUrl: "http://api",
      fetchImpl: async () => {
        throw new TypeError("fetch failed");
      },
    });
    const error = await client.health().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe("network_error");
  });

  it("streams chat events across chunk boundaries", async () => {
    const client = createApiClient({
      baseUrl: "http://api",
      fetchImpl: async () =>
        streamResponse([
          'event: meta\ndata: {"conversation_id":"c1"}\n\nevent: activity\ndata: {"stage":"searching"}\n\nevent: del',
          'ta\ndata: {"text":"Sal"}\n\nevent: delta\ndata: {"text":"om"}\n\n',
          'event: done\ndata: {"message":{"content":"Salom"}}\n\n',
        ]),
    });
    const events = [];
    for await (const event of client.streamChat({ message: "hi" })) events.push(event);
    expect(events.map((e) => e.type)).toEqual(["meta", "activity", "delta", "delta", "done"]);
    const text = events.flatMap((e) => (e.type === "delta" ? [e.data.text] : [])).join("");
    expect(text).toBe("Salom");
  });
});
