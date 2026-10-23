# Device acceptance evidence — desktop and Android MVP

- **Evidence source:** Devices workflow, run
  [39988632939](https://github.com/UmidjanDeveloper/EZO/actions/runs/39988632939).
- **Commit:** `40d2c40` on `claude/desktop-mobile-mvp`.
- **Runners:** GitHub-hosted `windows-latest` and `ubuntu-latest` virtual machines. These are
  real operating systems, **not the owner's physical PC or phone**, and have no microphone,
  no speakers and no AI keys.

## INSTALLABLE NOW

| Artifact | Evidence |
|---|---|
| `EZO-Setup-0.1.0.exe` (Windows x64, NSIS, **unsigned**) | Size 114.9 MB. Installed with `/S` to `C:\Users\runneradmin\AppData\Local\Programs\EZO\EZO.exe`. Artifact `ezo-windows`. |
| `EZO-debug.apk` (Android, package `uz.ezo.mobile`, minSdk 24, target 36) | Built with Gradle `assembleDebug`, label "EZO", sha256 `7a960b608ea9e18ae991c71408cc18551f39f20dfd0d99ab99106624fd410d6f`. Artifact `ezo-android`. **Not installed on any device or emulator yet.** |

## WORKING ON A REAL OS (Windows runner, the installed app's `--self-test`)

| Scenario | Result |
|---|---|
| B. Open Calculator | ok: the `win32calc` process is running after `openApp("calculator")` |
| C. Find a file in an allowed folder | ok: found `ezo-allowed\2026\Hisobot oktyabr 2026.txt`; the decoy file was not returned |
| D. Dictate into the focused app | ok: a focused text box received exactly `"Salom EZO! O‘zbekcha matn 2026."` (clipboard paste + restore). **Notepad** was activated (`Untitled - Notepad`), but its text could not be read back through UI Automation on the runner, so Notepad itself is **unverified**. |
| Volume keys | ok: SendKeys media keys completed (the runner has no audio device, so the volume change itself is not observable) |
| E (capture half). Screenshot | ok: 156,367-byte PNG of the primary screen. The *explanation* half needs an AI key; see below. |
| Uzbek command parsing | ok: "Kalkulyatorni och" → `open_app/calculator` |

## WORKING AGAINST A REAL EZO API (local, offline mode, no AI keys)

`EZO_LIVE_API=http://localhost:8091 vitest run src/main/live.test.ts`: **2/2 passed**.

- **H. A conversation started by the desktop client is continued from the phone client.**
  - The phone client listed the desktop conversation, added a message, and both messages are
    stored in the same conversation.
- **Honest failure without keys:**
  - `/api/voice/transcribe` returns `voice_not_configured`.
  - `/api/vision/describe` returns `vision_not_configured`.
  - The chat reply clearly says EZO is offline.

## WORKING ONLY IN TESTS

| Test suite | Result |
|---|---|
| Desktop unit tests | 44 (intents, actions, file containment, API client, assistant turns) |
| Mobile unit tests | 8 (API client, document reading) |
| API vision tests | 11 |
| Full API suite | 1205 passed |

## NOT YET DEMONSTRATED (needs the owner or keys)

- **A. Spoken Uzbek answered aloud.**
  - Needs a real microphone and speakers, plus `OPENAI_API_KEY` or `ELEVENLABS_API_KEY` (with
    a voice ID) on the server.
  - The pipeline is built and unit-tested; no live provider call was made.
- **E. Screen explanation.** Needs `GEMINI_API_KEY`, `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`
  on the server.
- **F. Install the APK and have an Uzbek voice conversation.** Needs a physical Android phone
  (or emulator) and a voice key.
- **G. Summarise a picked document.**
  - Implemented for TXT, MD and CSV; needs a phone and an AI key.
  - PDF and DOCX are **BLOCKED** until the isolated document executor is deployed (PR #33).

## BLOCKED

| Item | Reason |
|---|---|
| iOS | No macOS/Xcode build host and no Apple Developer account |
| Phone control | Not implemented (Android Accessibility consent) and impossible on iOS |
| Code signing | Needs the owner's certificate. Until then SmartScreen warns and the APK is debug-signed. |
| Device pairing, durable multi-step tasks, Telegram delivery, Downloads → PDF → Telegram | Phase 4, unchanged |

## EXACT NEXT ACTION (owner)

1. Run an EZO server.
   - The simplest option is `docker compose up` on the PC.
   - For the phone, use token mode on the LAN with `EZO_CORS_ORIGINS=https://localhost`.
   - Add one voice key and one AI key to the server's `.env`.
2. From the run above, download the `ezo-windows` artifact, install it, and in ⚙ enable
   Calculator, typing and one folder. Then press Ctrl+Alt+Space and say
   "Kalkulyatorni och". That covers scenario A + B on your own PC.
3. Download the `ezo-android` artifact, install the APK, enter the server URL and token, and
   tap 🎤. That covers scenario F.
4. Report what happened. Failures on real hardware are the next thing to fix.
