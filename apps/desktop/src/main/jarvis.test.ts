import { createPublicKey, verify } from "node:crypto";
import { mkdtemp, symlink, utimes, writeFile, mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  buildResult,
  canonical,
  generateDeviceKey,
  latestDocuments,
  PAIRING_DOMAIN,
  pairingRequest,
  RESULT_DOMAIN,
  validWork,
  type DeviceWork,
} from "./jarvis";

// Produced by the API's own `ezo_api.jarvis.device_protocol.canonical` for the same payload:
// the bytes the server verifies the device signature over.
const PYTHON_CANONICAL =
  '{"action":"files.latest_documents","device_id":"33333333-3333-4333-8333-333333333333","files":[{"content_base64":"aGVsbG8=","extension":"txt","modified_ms":1761300000123,"name":"Hisobot oktyabr — 2026.txt","sha256":"2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824","size_bytes":5}],"latest_ambiguous":false,"outcome":"completed","reason":null,"request_id":"11111111-1111-4111-8111-111111111111","schema_version":1,"task_id":"22222222-2222-4222-8222-222222222222","trust":"untrusted_file_content_not_instructions"}';

function publicKeyObject(hex: string) {
  // SPKI prefix for a raw 32-byte Ed25519 public key.
  const der = Buffer.concat([Buffer.from("302a300506032b6570032100", "hex"), Buffer.from(hex, "hex")]);
  return createPublicKey({ key: der, format: "der", type: "spki" });
}

const work = (count = 2): DeviceWork => ({
  schema_version: 1,
  request_id: "11111111-1111-4111-8111-111111111111",
  task_id: "22222222-2222-4222-8222-222222222222",
  device_id: "33333333-3333-4333-8333-333333333333",
  action: "files.latest_documents",
  root: "downloads",
  count,
  extensions: ["pdf", "docx", "xlsx", "pptx", "txt", "csv"],
  expires_at: Math.floor(Date.now() / 1000) + 60,
});

describe("JARVIS device companion", () => {
  it("serialises exactly like the server", () => {
    const payload = JSON.parse(PYTHON_CANONICAL);
    expect(canonical(payload)).toBe(PYTHON_CANONICAL);
  });

  it("signs pairing and results with a key that verifies as standard Ed25519", async () => {
    const key = generateDeviceKey();
    expect(key.publicKeyHex).toMatch(/^[a-f0-9]{64}$/);
    const pairing = pairingRequest(key, "Owner PC", "windows");
    const message = PAIRING_DOMAIN + canonical({ name: "Owner PC", nonce: pairing.nonce, platform: "windows" });
    expect(verify(null, Buffer.from(message), publicKeyObject(key.publicKeyHex), Buffer.from(pairing.signature, "hex"))).toBe(true);

    const dir = await mkdtemp(path.join(tmpdir(), "ezo-jarvis-"));
    await writeFile(path.join(dir, "a.txt"), "hello");
    const { files } = await latestDocuments(dir, 1, work().extensions);
    const signed = await buildResult(work(1), key, { files, ambiguous: false });
    const bytes = Buffer.from(RESULT_DOMAIN + canonical(signed.payload));
    expect(verify(null, bytes, publicKeyObject(key.publicKeyHex), Buffer.from(signed.signature, "hex"))).toBe(true);
    expect(JSON.stringify(signed.payload)).not.toContain(dir); // no local paths leave the PC
  });

  it("picks the newest supported files directly in the chosen folder only", async () => {
    const dir = await mkdtemp(path.join(tmpdir(), "ezo-jarvis-"));
    const at = async (name: string, seconds: number, content = "x") => {
      await writeFile(path.join(dir, name), content);
      await utimes(path.join(dir, name), seconds, seconds);
    };
    await at("old.txt", 1_000);
    await at("previous.docx", 2_000);
    await at("newest.xlsx", 3_000);
    await at("installer.exe", 9_000); // unsupported type
    await at("~$lock.docx", 9_000); // Office lock file
    await mkdir(path.join(dir, "sub"));
    await writeFile(path.join(dir, "sub", "deep.pdf"), "x"); // subfolders are not searched
    await symlink(path.join(dir, "old.txt"), path.join(dir, "link.pdf")).catch(() => undefined);
    const result = await latestDocuments(dir, 2, work().extensions);
    expect(result.files.map((f) => f.name)).toEqual(["newest.xlsx", "previous.docx"]);
    expect(result.ambiguous).toBe(false);
  });

  it("reports a tie instead of guessing", async () => {
    const dir = await mkdtemp(path.join(tmpdir(), "ezo-jarvis-"));
    for (const name of ["a.pdf", "b.pdf"]) {
      await writeFile(path.join(dir, name), "x");
      await utimes(path.join(dir, name), 5_000, 5_000);
    }
    expect((await latestDocuments(dir, 1, ["pdf"])).ambiguous).toBe(true);
  });

  it("accepts only well-formed, unexpired work for this device", () => {
    const now = Math.floor(Date.now() / 1000);
    expect(validWork(work(), work().device_id, now)).toBe(true);
    expect(validWork({ ...work(), device_id: "x" }, work().device_id, now)).toBe(false);
    expect(validWork({ ...work(), action: "shell.run" }, work().device_id, now)).toBe(false);
    expect(validWork({ ...work(), count: 50 }, work().device_id, now)).toBe(false);
    expect(validWork({ ...work(), expires_at: now - 1 }, work().device_id, now)).toBe(false);
  });

  it("can refuse with a signed reason", async () => {
    const key = generateDeviceKey();
    const signed = await buildResult(work(), key, { refused: "Owner declined" });
    expect(signed.payload.outcome).toBe("refused");
    expect(signed.payload.files).toEqual([]);
  });
});

describe("computer actions", () => {
  const base = {
    schema_version: 1 as const,
    request_id: "11111111-1111-4111-8111-111111111111",
    task_id: "22222222-2222-4222-8222-222222222222",
    device_id: "33333333-3333-4333-8333-333333333333",
    expires_at: 4_000_000_000,
  };

  it("accepts only the fixed actions, folders and this device", async () => {
    const { validPcWork } = await import("./jarvis");
    const ok = { ...base, action: "pc.open_app", root: "downloads", target: "calculator" };
    expect(validPcWork(ok, base.device_id, 1)).toBe(true);
    expect(validPcWork({ ...ok, action: "pc.run_command" }, base.device_id, 1)).toBe(false);
    expect(validPcWork({ ...ok, root: "system32" }, base.device_id, 1)).toBe(false);
    expect(validPcWork(ok, "other-device", 1)).toBe(false);
    expect(validPcWork({ ...ok, expires_at: 0 }, base.device_id, 1)).toBe(false);
  });

  it("never opens programs, scripts or paths outside the folder", async () => {
    const { safeFileName } = await import("./jarvis");
    expect(safeFileName("hisobot.docx")).toBe(true);
    expect(safeFileName("Oylik hisobot 2026.xlsx")).toBe(true);
    for (const bad of ["virus.exe", "run.bat", "x.ps1", "a.lnk", "../secret.docx", "C:\\\\x.docx", ".env", "noext"]) {
      expect(safeFileName(bad)).toBe(false);
    }
  });

  it("lists a folder and opens a file in it; refuses everything else", async () => {
    const { mkdtemp, writeFile, mkdir } = await import("node:fs/promises");
    const os = await import("node:os");
    const path = await import("node:path");
    const { runPcAction } = await import("./jarvis");
    const dir = await mkdtemp(path.join(os.tmpdir(), "ezo-pc-"));
    await writeFile(path.join(dir, "hisobot.docx"), "x");
    await writeFile(path.join(dir, "tool.exe"), "x");
    await mkdir(path.join(dir, "Rasmlar"));
    const opened: string[] = [];
    const deps = {
      folders: { downloads: dir, documents: dir, desktop: dir },
      openApp: async () => undefined,
      openPath: async (target: string) => (opened.push(target), ""),
      openExternal: async (url: string) => void opened.push(url),
    };
    const listed = await runPcAction({ ...base, action: "pc.list_folder", root: "downloads", target: null }, deps);
    expect("entries" in listed && listed.entries.map((e) => e.name).sort()).toEqual(["Rasmlar", "hisobot.docx", "tool.exe"]);
    expect(await runPcAction({ ...base, action: "pc.open_file", root: "downloads", target: "hisobot.docx" }, deps)).toEqual({ entries: [] });
    expect(opened).toEqual([path.join(dir, "hisobot.docx")]);
    expect("refused" in (await runPcAction({ ...base, action: "pc.open_file", root: "downloads", target: "tool.exe" }, deps))).toBe(true);
    expect("refused" in (await runPcAction({ ...base, action: "pc.open_file", root: "downloads", target: "missing.docx" }, deps))).toBe(true);
    expect("refused" in (await runPcAction({ ...base, action: "pc.open_url", root: "downloads", target: "http://x.uz" }, deps))).toBe(true);
    expect("refused" in (await runPcAction({ ...base, action: "pc.open_app", root: "downloads", target: "cmd" }, deps))).toBe(true);
  });

  it("signs the result exactly like the server checks it (entries only when present)", async () => {
    const { buildPcResult, canonical, generateDeviceKey, RESULT_DOMAIN } = await import("./jarvis");
    const { createPublicKey, verify } = await import("node:crypto");
    const key = generateDeviceKey();
    const work = { ...base, action: "pc.open_app" as const, root: "downloads" as const, target: "calculator" };
    const done = buildPcResult(work, key, { entries: [] });
    expect("entries" in done.payload).toBe(false);
    expect(canonical(done.payload)).toBe(
      '{"action":"pc.open_app","device_id":"33333333-3333-4333-8333-333333333333","files":[],' +
        '"latest_ambiguous":false,"outcome":"completed","reason":null,' +
        '"request_id":"11111111-1111-4111-8111-111111111111","schema_version":1,' +
        '"task_id":"22222222-2222-4222-8222-222222222222","trust":"untrusted_file_content_not_instructions"}',
    );
    const publicKey = createPublicKey(createPublicKey({ key: key.privateKeyPem, format: "pem" }).export({ format: "pem", type: "spki" }));
    expect(verify(null, Buffer.from(RESULT_DOMAIN + canonical(done.payload)), publicKey, Buffer.from(done.signature, "hex"))).toBe(true);
    const listed = buildPcResult({ ...work, action: "pc.list_folder" }, key, { entries: [{ name: "a.docx", is_dir: false, size_bytes: 1, modified_ms: 2 }] });
    expect(listed.payload.entries).toEqual([{ name: "a.docx", is_dir: false, size_bytes: 1, modified_ms: 2 }]);
  });
});
