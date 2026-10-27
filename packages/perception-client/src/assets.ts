import { validateAssets, type VisionAssets } from "@ezo/face-tracking";

export type AssetsReadiness = { ready: true; assets: VisionAssets } | { ready: false; reason: "missing" | "invalid" | "network"; detail: string };

/**
 * Reads the app's `vision-assets.json` (written at build time by scripts/vision-assets.mjs)
 * and validates it against the engine's pins. The heavy files are only fetched and
 * SHA256-checked by the engine's worker when the owner presses the camera button.
 * `ready: false` is the honest reason the camera control shows.
 */
export async function loadVisionAssets(base: string, fetchImpl: typeof fetch = fetch): Promise<AssetsReadiness> {
  let response: Response;
  try {
    response = await fetchImpl(`${base}vision-assets.json`, { credentials: "omit", cache: "no-store" });
  } catch (error) {
    return { ready: false, reason: "network", detail: (error as Error).message };
  }
  if (response.status === 404) return { ready: false, reason: "missing", detail: "vision-assets.json not bundled" };
  if (!response.ok) return { ready: false, reason: "network", detail: `HTTP ${response.status}` };
  try {
    const assets = (await response.json()) as VisionAssets;
    validateAssets(assets, typeof location !== "undefined" ? location.href : base);
    return { ready: true, assets };
  } catch (error) {
    return { ready: false, reason: "invalid", detail: (error as Error).message };
  }
}
