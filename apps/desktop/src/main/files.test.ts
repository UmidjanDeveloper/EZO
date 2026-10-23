import { mkdirSync, mkdtempSync, symlinkSync, utimesSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { findFiles, isInsideAllowed } from "./files";

function sandbox() {
  const base = mkdtempSync(path.join(tmpdir(), "ezo-files-"));
  const allowed = path.join(base, "Hujjatlar");
  const secret = path.join(base, "Maxfiy");
  mkdirSync(path.join(allowed, "2026", "oktyabr"), { recursive: true });
  mkdirSync(secret);
  writeFileSync(path.join(allowed, "Hisobot_2025.docx"), "old");
  writeFileSync(path.join(allowed, "2026", "oktyabr", "Hisobot 2026 yakuniy.pdf"), "new");
  writeFileSync(path.join(allowed, "rezyume.txt"), "cv");
  writeFileSync(path.join(secret, "hisobot parollar.txt"), "secret");
  utimesSync(path.join(allowed, "Hisobot_2025.docx"), new Date(2025, 0, 1), new Date(2025, 0, 1));
  return { base, allowed, secret };
}

describe("findFiles", () => {
  it("matches every word of the query in names, newest first, only inside allowed folders", async () => {
    const { allowed } = sandbox();
    const hits = await findFiles("hisobot", [allowed]);
    expect(hits.map((h) => h.name)).toEqual(["Hisobot 2026 yakuniy.pdf", "Hisobot_2025.docx"]);
    expect((await findFiles("hisobot 2026", [allowed])).map((h) => h.name)).toEqual(["Hisobot 2026 yakuniy.pdf"]);
  });

  it("never returns files from folders that were not allowed, even via a symlink", async () => {
    const { allowed, secret } = sandbox();
    try {
      symlinkSync(secret, path.join(allowed, "link-to-secret"), "dir");
    } catch {
      // symlinks may need privileges on Windows; the containment check below still applies
    }
    const hits = await findFiles("parollar", [allowed]);
    expect(hits).toEqual([]);
  });

  it("returns nothing for an empty query or no allowed folder", async () => {
    const { allowed } = sandbox();
    expect(await findFiles("  ", [allowed])).toEqual([]);
    expect(await findFiles("hisobot", [])).toEqual([]);
  });
});

describe("isInsideAllowed", () => {
  it("accepts files inside an allowed folder and refuses traversal or other folders", async () => {
    const { allowed, secret } = sandbox();
    expect(await isInsideAllowed(path.join(allowed, "rezyume.txt"), [allowed])).toBe(true);
    expect(await isInsideAllowed(path.join(allowed, "..", "Maxfiy", "hisobot parollar.txt"), [allowed])).toBe(false);
    expect(await isInsideAllowed(path.join(secret, "hisobot parollar.txt"), [allowed])).toBe(false);
    expect(await isInsideAllowed(path.join(allowed, "missing.txt"), [allowed])).toBe(false);
  });
});
