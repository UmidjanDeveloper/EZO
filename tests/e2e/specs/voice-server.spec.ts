import { expect, test, type Page } from "@playwright/test";

/**
 * Server voice (e.g. VoiceStudio or OpenAI behind EZO's /api/voice): the microphone is a
 * synthetic tone that "speaks" briefly and then goes quiet; the voice API is mocked.
 */

function silentWav(seconds: number): Buffer {
  const rate = 8000;
  const samples = Math.round(rate * seconds);
  const buffer = Buffer.alloc(44 + samples * 2);
  buffer.write("RIFF", 0);
  buffer.writeUInt32LE(36 + samples * 2, 4);
  buffer.write("WAVEfmt ", 8);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20);
  buffer.writeUInt16LE(1, 22);
  buffer.writeUInt32LE(rate, 24);
  buffer.writeUInt32LE(rate * 2, 28);
  buffer.writeUInt16LE(2, 32);
  buffer.writeUInt16LE(16, 34);
  buffer.write("data", 36);
  buffer.writeUInt32LE(samples * 2, 40);
  return buffer;
}

async function fakeMicrophoneAndBrowserSpeech(page: Page) {
  await page.addInitScript(() => {
    const w = window as unknown as Record<string, unknown>;
    w.__ezoSpoken = [];
    w.__ezoBrowserHeard = ["Salom, brauzer orqali gapiryapman"];
    navigator.mediaDevices.getUserMedia = async () => {
      const context = new AudioContext();
      await context.resume();
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      gain.gain.setValueAtTime(0.6, context.currentTime);
      gain.gain.setValueAtTime(0, context.currentTime + 0.7); // "speech" for 0.7 s, then silence
      const destination = context.createMediaStreamDestination();
      oscillator.connect(gain).connect(destination);
      oscillator.start();
      return destination.stream;
    };
    class FakeRecognition {
      lang = "";
      onresult: ((event: unknown) => void) | null = null;
      onerror: ((event: unknown) => void) | null = null;
      onend: (() => void) | null = null;
      continuous = false;
      interimResults = false;
      start() {
        const said = (w.__ezoBrowserHeard as string[]).shift();
        setTimeout(() => {
          if (said) this.onresult?.({ resultIndex: 0, results: [Object.assign([{ transcript: said }], { isFinal: true })] });
          else this.onerror?.({ error: "no-speech" });
          this.onend?.();
        }, (w.__ezoRecognitionDelay as number | undefined) ?? 100);
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
  await page.route("**/api/voice/status", (route) =>
    route.fulfill({
      json: {
        speech_to_text: ["voicestudio"],
        text_to_speech: ["voicestudio"],
        realtime: false,
        max_audio_mb: 10,
        stores_audio: false,
        browser_fallback: true,
      },
    }),
  );
}

test("server voice: record, transcribe, answer, speak; tap to interrupt", async ({ page }) => {
  await fakeMicrophoneAndBrowserSpeech(page);
  const transcripts = ["Salom EZO, qalaysan?", ""];
  let uploads = 0;
  let speakRequests = 0;
  await page.route("**/api/voice/transcribe", async (route) => {
    uploads += 1;
    const body = route.request().postDataBuffer() ?? Buffer.alloc(0);
    expect(body.includes(Buffer.from('name="audio"'))).toBe(true);
    await route.fulfill({ json: { text: transcripts.shift() ?? "", language: "uz", provider: "voicestudio", attempts: [] } });
  });
  await page.route("**/api/voice/speak", async (route) => {
    speakRequests += 1;
    await route.fulfill({ body: silentWav(4), contentType: "audio/wav", headers: { "X-EZO-Voice-Provider": "voicestudio" } });
  });

  await page.goto("/");
  await page.getByTestId("mode-voice").click();
  const stage = page.getByTestId("voice-stage");
  await expect(stage).toHaveAttribute("data-engine", "server");
  await page.getByTestId("voice-toggle").click();
  await expect(page.getByTestId("voice-status")).toHaveText("Tinglayapman…");

  await expect(page.getByTestId("voice-heard")).toContainText("Salom EZO, qalaysan?", { timeout: 10_000 });
  await expect(page.getByTestId("voice-caption")).toContainText("oflayn rejimda");
  await expect(stage.getByTestId("ezo-presence")).toHaveAttribute("data-state", "speaking");
  expect(speakRequests).toBe(1);

  // Barge-in: tap the robot while EZO speaks → it stops and listens.
  await stage.getByRole("button", { name: "Gapiryapman… (bo‘lish uchun bosing)" }).click();
  await expect(page.getByTestId("voice-status")).toHaveText("Tinglayapman…");
  await expect(page.getByTestId("voice-status")).toHaveText("Gaplashish uchun robotga bosing", { timeout: 10_000 });
  expect(uploads).toBe(2);
  const browserSpoken = await page.evaluate(() => (window as unknown as { __ezoSpoken: string[] }).__ezoSpoken);
  expect(browserSpoken).toEqual([]); // the server voice spoke, not the browser
});

test("server voice failure falls back to the browser for listening and speaking", async ({ page }) => {
  await fakeMicrophoneAndBrowserSpeech(page);
  await page.addInitScript(() => {
    (window as unknown as Record<string, unknown>).__ezoRecognitionDelay = 1500;
  });
  await page.route("**/api/voice/transcribe", (route) =>
    route.fulfill({ status: 502, json: { error: { code: "voice_failed", message: "No voice provider could handle the request." } } }),
  );
  await page.route("**/api/voice/speak", (route) =>
    route.fulfill({ status: 502, json: { error: { code: "voice_failed", message: "down" } } }),
  );

  await page.goto("/");
  await page.getByTestId("mode-voice").click();
  await page.getByTestId("voice-toggle").click();

  await expect(page.getByRole("status").filter({ hasText: "Server ovozi hozir ishlamayapti" })).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("voice-stage")).toHaveAttribute("data-engine", "browser");
  await expect(page.getByTestId("voice-heard")).toContainText("Salom, brauzer orqali gapiryapman");
  await expect(page.getByTestId("voice-caption")).toContainText("oflayn rejimda");
  await expect
    .poll(() => page.evaluate(() => (window as unknown as { __ezoSpoken: string[] }).__ezoSpoken.length))
    .toBeGreaterThan(0); // the reply was read by the browser voice after the server voice failed
});
