import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { strings, UI_LANGUAGES } from "../../../apps/desktop/src/main/strings";

// Accessibility scan (axe-core, WCAG 2.x A/AA rules) of the pages a person meets first, in
// the real built app. Any "serious" or "critical" violation fails; the whole list is printed
// so a failure names the element. The scan is objective evidence for the a11y claims in
// docs/master/EZO_PRODUCT_COMPLETION.md; it is not a substitute for a screen-reader session.

const PILL = path.resolve(__dirname, "../../../apps/desktop/dist/pill.html");
const SETTINGS = path.resolve(__dirname, "../../../apps/desktop/dist/settings.html");
const EXTENSION_POPUP = path.resolve(__dirname, "../../../apps/chrome-extension/popup.html");
const MOBILE_DIST = path.resolve(__dirname, "../../../apps/mobile/dist");

async function scan(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  const describe = (v: (typeof results.violations)[number]) =>
    `${v.id} (${v.impact}): ${v.help} — ${v.nodes
      .slice(0, 8)
      .map((n) => {
        const data = n.any[0]?.data as { fgColor?: string; bgColor?: string; contrastRatio?: number; expectedContrastRatio?: string } | undefined;
        const colours = data?.contrastRatio ? ` [${data.fgColor} on ${data.bgColor} = ${data.contrastRatio}, needs ${data.expectedContrastRatio}]` : "";
        return `${n.target.join(" ")}${colours}`;
      })
      .join("; ")}`;
  if (results.violations.length) console.log(`axe ${page.url()}\n  ${results.violations.map(describe).join("\n  ")}`);
  expect(serious.map(describe)).toEqual([]);
  return results;
}

const pages: [string, string][] = [
  ["home (humanoid + composer)", "/"],
  ["student", "/student"],
  ["ielts", "/ielts"],
  ["settings", "/settings"],
  ["jarvis console", "/jarvis"],
  ["memory", "/memory"],
];

for (const [name, url] of pages) {
  test(`a11y: ${name} has no serious or critical axe violations`, async ({ page }) => {
    await page.goto(url);
    await page.waitForLoadState("networkidle");
    await scan(page);
  });
}

test("a11y: the voice stage with the humanoid is operable by keyboard and named for screen readers", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("mode-voice").click();
  await expect(page.getByTestId("voice-stage")).toBeVisible();
  const face = page.getByTestId("voice-stage").getByTestId("ezo-humanoid");
  await expect(face).toHaveAttribute("role", "img");
  await expect(face).toHaveAttribute("aria-label", /^EZO — \S/);
  await expect(face.locator("canvas")).toHaveAttribute("aria-hidden", "true");
  await scan(page);
  // The talk control and the mode tabs work without a pointer.
  await page.getByTestId("voice-toggle").focus();
  await expect(page.getByTestId("voice-toggle")).toBeFocused();
  await page.getByTestId("mode-text").focus();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("voice-stage")).toHaveCount(0);
});

test("a11y: the desktop pill renderer has no serious or critical axe violations", async ({ page }) => {
  test.skip(!existsSync(PILL), "apps/desktop not built (desktop-pill.spec builds it first in the full run)");
  await page.goto(`file://${PILL}`);
  await expect(page.locator("#pill")).toHaveClass(/idle|offline|error/);
  await scan(page);
});

test("a11y: the Android app's welcome and settings screens have no serious or critical axe violations", async ({ page }) => {
  test.skip(!existsSync(path.join(MOBILE_DIST, "index.html")), "apps/mobile not built (pnpm -C apps/mobile build)");
  // The Vite build is served from memory on a fake origin, exactly as the WebView loads it.
  await page.route("http://ezo-mobile.test/**", (route) => {
    const file = path.join(MOBILE_DIST, new URL(route.request().url()).pathname.replace(/^\/$/, "/index.html"));
    if (!existsSync(file)) return route.fulfill({ status: 404 });
    const type = file.endsWith(".js") ? "text/javascript" : file.endsWith(".css") ? "text/css" : "text/html";
    return route.fulfill({ body: readFileSync(file), contentType: type });
  });
  await page.goto("http://ezo-mobile.test/");
  await expect(page.locator("#welcomeTab")).toBeVisible();
  await scan(page);
  await page.locator("#welcomeStart").click();
  await expect(page.locator("#welcomeTab")).toBeHidden();
  await scan(page);
});

test("a11y: the desktop settings window has no serious or critical axe violations", async ({ page }) => {
  test.skip(!existsSync(SETTINGS), "apps/desktop not built");
  // The real renderer with the main-process bridge replaced by a fake that answers like the
  // main process does (the same strings table, default settings, no token, not paired).
  const settings = {
    apiUrl: "http://localhost:8000", language: "uz", allowedFolders: ["C:\\Users\\Owner\\Documents"],
    apps: { calculator: true, notepad: false, paint: false, explorer: false }, allowTyping: false, allowScreen: false,
    allowVolume: false, speakReplies: true, shortcut: "Control+Alt+Space", conversationId: null, jarvisFolder: null, jarvisDeviceId: null,
  };
  await page.addInitScript(
    ({ settings, strings, languages }) => {
      (window as unknown as Record<string, unknown>).ezoSettings = {
        get: async () => ({ settings, hasToken: false, secureStorage: true, shortcuts: ["Control+Alt+Space"], platform: "win32", strings, languages }),
        save: async () => settings,
        setToken: async () => undefined,
        addFolder: async () => settings,
        removeFolder: async () => settings,
        forgetConversation: async () => settings,
        test: async () => ({ ok: false, message: "offline in this test" }),
        jarvisChooseFolder: async () => settings,
        jarvisClearFolder: async () => settings,
        jarvisPair: async () => ({ ok: false }),
        jarvisUnpair: async () => settings,
        jarvisStatus: async () => ({ paired: false, status: "unpaired" }),
      };
    },
    { settings, strings: strings("uz").settings, languages: UI_LANGUAGES },
  );
  await page.goto(`file://${SETTINGS}`);
  await expect(page.locator("#language")).toHaveValue("uz");
  await expect(page.locator("#folders")).toContainText("Documents");
  await scan(page);
});

test("a11y: the Chrome extension popup has no serious or critical axe violations", async ({ page }) => {
  // Static markup only: chrome.* is absent here, so popup.js stops at its first storage call,
  // which is exactly the state before the person clicks anything.
  await page.goto(`file://${EXTENSION_POPUP}`);
  await expect(page.locator("#checkBackendBtn")).toBeVisible();
  await scan(page);
});
