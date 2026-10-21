import { afterEach, expect, it, vi } from "vitest";
import { hasNextStudentPage, studentRequest } from "./student-api";

vi.mock("./api", () => ({ apiUrl: () => "http://api.test", storedToken: { get: () => " private-test-token " } }));
afterEach(() => vi.unstubAllGlobals());
it("authenticates private Student requests and disables browser caching", async () => {
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ state: "queued" }) });
  vi.stubGlobal("fetch", fetcher);
  expect(await studentRequest("student/library")).toEqual({ state: "queued" });
  const [url, init] = fetcher.mock.calls[0];
  expect(url).toBe("http://api.test/api/student/library");
  expect(init.headers.get("Authorization")).toBe("Bearer private-test-token");
  expect(init.cache).toBe("no-store");
});
it("shows structured safe API errors", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, json: async () => ({ detail: { code: "input_limit", message: "Maximum 5 MiB." } }) }));
  await expect(studentRequest("student/uploads")).rejects.toThrow("Maximum 5 MiB.");
});

it("keeps the last page reachable when text contains astral Unicode", () => {
  expect(hasNextStudentPage({ offset: 0, text: "🙂".repeat(4000), total_chars: 4001 })).toBe(true);
  expect(hasNextStudentPage({ offset: 4000, text: "Ў", total_chars: 4001 })).toBe(false);
  expect(hasNextStudentPage({ offset: 9000, text: "", total_chars: 4001 })).toBe(false);
});
