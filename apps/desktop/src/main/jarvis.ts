/**
 * JARVIS device companion: pairing key, the one fixed action, and signed results.
 *
 * - The Ed25519 key is generated here and never leaves this computer (stored encrypted
 *   by the OS). Only the public half is registered with EZO at pairing.
 * - The only action is `files.latest_documents`: the newest supported documents placed
 *   DIRECTLY in the folder the owner chose for JARVIS (no subfolders, no symlinks,
 *   no paths sent to the server, at most 2 files of at most 5 MiB).
 * - Results are signed over canonical JSON that matches the server byte for byte.
 */
import { createHash, generateKeyPairSync, randomBytes, sign, createPrivateKey } from "node:crypto";
import { lstat, readdir, readFile } from "node:fs/promises";
import path from "node:path";

export const RESULT_DOMAIN = "ezo-jarvis-device-result-v1\u0000";
export const PAIRING_DOMAIN = "ezo-jarvis-device-pairing-v1\u0000";
export const MAX_FILE_BYTES = 5 * 1024 * 1024;
export const DEVICE_EXTENSIONS = ["pdf", "docx", "xlsx", "pptx", "txt", "csv"] as const;
const MAX_ENTRIES = 5_000;

export interface DeviceKey {
  publicKeyHex: string;
  privateKeyPem: string;
}

export interface DeviceWork {
  schema_version: 1;
  request_id: string;
  task_id: string;
  device_id: string;
  action: "files.latest_documents";
  root: "downloads";
  count: number;
  extensions: string[];
  expires_at: number;
}

export interface LocalFile {
  name: string;
  extension: string;
  size: number;
  modifiedMs: number;
  fullPath: string;
}

export function generateDeviceKey(): DeviceKey {
  const { publicKey, privateKey } = generateKeyPairSync("ed25519");
  const spki = publicKey.export({ format: "der", type: "spki" });
  return {
    publicKeyHex: Buffer.from(spki.subarray(spki.length - 32)).toString("hex"),
    privateKeyPem: privateKey.export({ format: "pem", type: "pkcs8" }).toString(),
  };
}

/** JSON exactly like Python's json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False). */
export function canonical(value: unknown): string {
  if (value === null || typeof value !== "object") {
    if (typeof value === "number" && !Number.isInteger(value)) throw new Error("only integers");
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  const entries = Object.entries(value as Record<string, unknown>)
    .filter(([, v]) => v !== undefined)
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${canonical(v)}`).join(",")}}`;
}

function signText(text: string, privateKeyPem: string): string {
  return sign(null, Buffer.from(text, "utf8"), createPrivateKey(privateKeyPem)).toString("hex");
}

export function pairingRequest(key: DeviceKey, name: string, platform: "windows" | "linux") {
  const nonce = randomBytes(16).toString("hex");
  const message = PAIRING_DOMAIN + canonical({ name, nonce, platform });
  return {
    name,
    platform,
    public_key: key.publicKeyHex,
    nonce,
    signature: signText(message, key.privateKeyPem),
    capabilities: ["files.latest_documents"],
  };
}

export interface LatestResult {
  files: LocalFile[];
  ambiguous: boolean;
}

/** Newest supported regular files directly inside `folder` (the owner's chosen folder). */
export async function latestDocuments(folder: string, count: number, extensions: readonly string[]): Promise<LatestResult> {
  const allowed = new Set(extensions.filter((e) => (DEVICE_EXTENSIONS as readonly string[]).includes(e)));
  const entries = (await readdir(folder, { withFileTypes: true })).slice(0, MAX_ENTRIES);
  const files: LocalFile[] = [];
  for (const entry of entries) {
    if (!entry.isFile() || entry.isSymbolicLink() || entry.name.startsWith("~$") || entry.name.startsWith(".")) continue;
    const extension = path.extname(entry.name).slice(1).toLowerCase();
    if (!allowed.has(extension)) continue;
    const fullPath = path.join(folder, entry.name);
    try {
      const info = await lstat(fullPath);
      if (!info.isFile() || info.size === 0 || info.size > MAX_FILE_BYTES) continue;
      files.push({ name: entry.name, extension, size: info.size, modifiedMs: Math.floor(info.mtimeMs), fullPath });
    } catch {
      // vanished between readdir and lstat
    }
  }
  files.sort((a, b) => b.modifiedMs - a.modifiedMs);
  const chosen = files.slice(0, count);
  // Ambiguous when the file just outside the selection is as new as the last one chosen,
  // or when the newest two tie: EZO must not guess which one the owner meant.
  const ambiguous =
    (files.length > count && files[count]!.modifiedMs === chosen[count - 1]!.modifiedMs) ||
    (chosen.length >= 2 && chosen[0]!.modifiedMs === chosen[1]!.modifiedMs);
  return { files: chosen, ambiguous };
}

export interface SignedResult {
  payload: Record<string, unknown>;
  signature: string;
}

export async function buildResult(
  work: DeviceWork,
  key: DeviceKey,
  outcome: { files: LocalFile[]; ambiguous: boolean } | { refused: string },
): Promise<SignedResult> {
  const base = {
    schema_version: 1,
    request_id: work.request_id,
    task_id: work.task_id,
    device_id: work.device_id,
    action: "files.latest_documents",
    trust: "untrusted_file_content_not_instructions",
  };
  let payload: Record<string, unknown>;
  if ("refused" in outcome) {
    payload = { ...base, outcome: "refused", reason: outcome.refused.slice(0, 200), files: [], latest_ambiguous: false };
  } else {
    const files = [];
    for (const file of outcome.files) {
      const data = await readFile(file.fullPath);
      if (data.length !== file.size) throw new Error("file changed while reading");
      files.push({
        name: file.name,
        extension: file.extension,
        size_bytes: data.length,
        modified_ms: file.modifiedMs,
        sha256: createHash("sha256").update(data).digest("hex"),
        content_base64: data.toString("base64"),
      });
    }
    payload = { ...base, outcome: "completed", reason: null, files, latest_ambiguous: outcome.ambiguous };
  }
  return { payload, signature: signText(RESULT_DOMAIN + canonical(payload), key.privateKeyPem) };
}

export function validWork(value: unknown, deviceId: string, nowSeconds: number): value is DeviceWork {
  const w = value as DeviceWork;
  return (
    !!w &&
    w.schema_version === 1 &&
    w.action === "files.latest_documents" &&
    w.root === "downloads" &&
    w.device_id === deviceId &&
    Number.isInteger(w.count) &&
    w.count >= 1 &&
    w.count <= 2 &&
    typeof w.request_id === "string" &&
    typeof w.task_id === "string" &&
    Array.isArray(w.extensions) &&
    typeof w.expires_at === "number" &&
    w.expires_at > nowSeconds
  );
}
