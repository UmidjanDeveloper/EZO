// Opening a generated file on the phone: the bytes are written to the app's own cache
// directory (private to EZO) and handed to Android's share sheet, which lets the owner
// pick Word, a PDF viewer, Telegram… Nothing is written to public storage.
import { Capacitor } from "@capacitor/core";
import { Directory, Filesystem } from "@capacitor/filesystem";
import { Share } from "@capacitor/share";

function toBase64(bytes: Uint8Array): string {
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  return btoa(binary);
}

/** A file name Android and the share sheet accept: no path separators or control characters. */
export function safeFilename(name: string, fallback = "ezo-file"): string {
  const cleaned = name.replace(/[\\/:*?"<>|\u0000-\u001f]+/g, "_").replace(/^\.+/, "").trim().slice(0, 120);
  return cleaned || fallback;
}

export async function openOrShare(blob: Blob, filename: string, title: string): Promise<"shared" | "downloaded"> {
  const name = safeFilename(filename);
  if (!Capacitor.isNativePlatform()) {
    // Plain browser (development): a normal download.
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
    return "downloaded";
  }
  const bytes = new Uint8Array(await blob.arrayBuffer());
  const written = await Filesystem.writeFile({ path: `ezo-share/${name}`, data: toBase64(bytes), directory: Directory.Cache, recursive: true });
  await Share.share({ title, files: [written.uri] });
  return "shared";
}
