import { createHash } from "node:crypto";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { chromium, expect, test } from "@playwright/test";

// Loads the real unpacked MV3 extension in Chromium and checks what it can do by default.
const EXT = path.resolve(__dirname, "../../../apps/chrome-extension");

/** Chrome's id for an unpacked extension: sha256 of its absolute path, hex digits a–p. */
function unpackedId(dir: string): string {
  const hex = createHash("sha256").update(dir).digest("hex").slice(0, 32);
  return [...hex].map((c) => String.fromCharCode("a".charCodeAt(0) + parseInt(c, 16))).join("");
}

test("extension: loads in Chromium with no host access and click-only controls", async () => {
  test.skip(test.info().project.name !== "desktop", "one browser run is enough");
  const context = await chromium.launchPersistentContext(mkdtempSync(path.join(tmpdir(), "ezo-ext-")), {
    channel: "chromium",
    headless: true,
    args: [`--disable-extensions-except=${EXT}`, `--load-extension=${EXT}`],
  });
  try {
    const page = await context.newPage();
    await page.goto(`chrome-extension://${unpackedId(EXT)}/popup.html`);
    await expect(page.getByRole("button", { name: "Sahifani qisqacha bayon qil" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Tanlangan matnni tushuntir" })).toBeVisible();
    await expect(page.locator("#sendBtn")).toBeHidden(); // nothing to send before a preview

    const granted = await page.evaluate(async () => {
      const all = await chrome.permissions.getAll();
      return { permissions: [...(all.permissions ?? [])].sort(), origins: all.origins ?? [] };
    });
    expect(granted.permissions).toEqual(["activeTab", "scripting", "storage"]);
    expect(granted.origins).toEqual([]); // no site, not even the local API, until the user allows it
    const manifest = await page.evaluate(() => chrome.runtime.getManifest());
    expect(manifest.manifest_version).toBe(3);
    expect(manifest.background).toBeUndefined();
    expect(manifest.content_scripts).toBeUndefined();

    // Only loopback servers are accepted in the settings.
    await page.fill("#apiBase", "https://evil.example");
    await page.click("#saveServer");
    await expect(page.locator("#answer")).toContainText("localhost");
  } finally {
    await context.close();
  }
});
