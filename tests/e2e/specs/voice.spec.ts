import { expect, test } from "@playwright/test";

/**
 * The browser's speech services are replaced with deterministic fakes:
 * the "microphone" hears one sentence, and spoken replies are recorded.
 */
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    const w = window as unknown as Record<string, unknown>;
    w.__ezoUtterances = ["Salom EZO, qalaysan?"];
    w.__ezoSpoken = [];
    w.__ezoLangs = [];

    class FakeRecognition {
      lang = "";
      continuous = false;
      interimResults = false;
      onresult: ((event: unknown) => void) | null = null;
      onerror: ((event: unknown) => void) | null = null;
      onend: (() => void) | null = null;
      start() {
        (w.__ezoLangs as string[]).push(this.lang);
        const said = (w.__ezoUtterances as string[]).shift();
        setTimeout(() => {
          if (said) {
            const result = Object.assign([{ transcript: said }], { isFinal: true });
            this.onresult?.({ resultIndex: 0, results: [result] });
          } else {
            this.onerror?.({ error: "no-speech" });
          }
          this.onend?.();
        }, 100);
      }
      stop() {}
      abort() {}
    }
    w.SpeechRecognition = FakeRecognition;
    w.webkitSpeechRecognition = FakeRecognition;

    const synth = window.speechSynthesis;
    synth.getVoices = () => [];
    synth.cancel = () => undefined;
    synth.speak = (utterance: SpeechSynthesisUtterance) => {
      (w.__ezoSpoken as string[]).push(utterance.text);
      setTimeout(() => utterance.onend?.(new Event("end") as SpeechSynthesisEvent), 100);
    };
  });
});

test("voice: talk to EZO like to a person", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("mode-voice").click();
  await expect(page.getByTestId("voice-stage")).toBeVisible();
  await expect(page.getByTestId("voice-stage").getByTestId("ezo-humanoid")).toHaveAttribute("data-state", "idle");

  await page.getByTestId("voice-toggle").click();

  // EZO heard the sentence, answered, and spoke the answer aloud.
  await expect(page.getByTestId("voice-heard")).toContainText("Salom EZO, qalaysan?");
  await expect(page.getByTestId("voice-caption")).toContainText("oflayn rejimda");
  await expect
    .poll(() => page.evaluate(() => (window as unknown as { __ezoSpoken: string[] }).__ezoSpoken.length))
    .toBeGreaterThan(0);
  const spoken = await page.evaluate(() => (window as unknown as { __ezoSpoken: string[] }).__ezoSpoken[0]);
  expect(spoken).toContain("oflayn rejimda");
  expect(spoken).not.toContain("**"); // Markdown is not read aloud

  // It listened again afterwards (hands-free), then stopped on silence.
  await expect(page.getByTestId("voice-status")).toHaveText("Gaplashish uchun robotga bosing");
  const langs = await page.evaluate(() => (window as unknown as { __ezoLangs: string[] }).__ezoLangs);
  expect(langs).toEqual(["uz-UZ", "uz-UZ"]);

  // The spoken exchange is part of the normal chat history.
  await page.getByTestId("mode-text").click();
  await expect(page.getByTestId("message-user")).toContainText("Salom EZO, qalaysan?");
  await expect(page.getByTestId("message-assistant")).toContainText("oflayn rejimda");
  await expect(page).toHaveURL(/\/chat\/[0-9a-f-]{36}$/);
});

test("voice: the composer microphone opens voice mode", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("composer-voice").click();
  await expect(page.getByTestId("voice-stage")).toBeVisible();
});

test("voice: immersive holographic stage fills the viewport, has no camera and keeps clap available", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("mode-voice").click();
  await expect(page.getByTestId("voice-stage").getByTestId("ezo-humanoid")).toHaveAttribute("data-style", "holographic");
  await page.getByTestId("voice-settings").locator(":scope > summary").click();
  await expect(page.getByTestId("camera-toggle")).toHaveCount(0);
  await expect(page.getByTestId("clap-toggle")).toBeEnabled();
  await expect(page.getByTestId("voice-frame")).toHaveCount(0);
  await page.getByTestId("voice-settings").locator(":scope > summary").click();
  for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    const scene = await page.getByTestId("voice-scene").boundingBox();
    const controls = await page.getByTestId("voice-controls").boundingBox();
    expect(scene).not.toBeNull(); expect(controls).not.toBeNull();
    expect(scene!.x).toBe(0); expect(scene!.y).toBe(0);
    expect(scene!.width).toBe(viewport.width);
    expect(scene!.height).toBe(viewport.height);
    expect(controls!.y).toBeGreaterThan(viewport.height * 0.6);
    await expect(page.getByTestId("camera-toggle")).not.toBeVisible();
    await expect(page.getByTestId("voice-sensor-status")).toBeVisible();
  }
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("voice-stage")).toHaveCount(0);
  await expect(page.getByTestId("mode-voice")).toBeVisible();
});
