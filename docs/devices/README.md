# EZO on Windows and Android — owner guide

The same EZO account, conversations, projects and memory are used by the web app, the
Windows app (`apps/desktop`) and the Android app (`apps/mobile`). All three talk to one
EZO API server. **Nothing here deploys a server or spends money.**

## 1. EZO server (needed first)

Both apps need a running EZO API.

| Situation | What to run | App setting |
|---|---|---|
| Testing on one PC | `docker compose up` in the repo, or `python scripts/ezo.py dev` | Desktop: `http://localhost:8000`, no token |
| Phone on the same Wi-Fi | API in **token mode**, listening on the LAN: `EZO_AUTH_MODE=token EZO_API_TOKEN=<32+ random chars> EZO_CORS_ORIGINS=https://localhost uvicorn ezo_api.main:create_app --factory --host 0.0.0.0 --port 8000` | Phone: `http://192.168.x.y:8000` and the same token (debug APK only) |
| Later, real deployment | `deploy/primary` (see `docs/deployment/OWNER_ACTIVATION_CHECKLIST.md`) | `https://api.<your-domain>` and the token |

- **CORS for the phone.** The phone app runs at the origin `https://localhost` inside its
  WebView, so that origin must be in `EZO_CORS_ORIGINS`. The desktop app sends its requests
  from the main process and needs no CORS entry.
- **Voice and screen/photo understanding need keys on the server.**
  - Voice in Uzbek needs `OPENAI_API_KEY` or `ELEVENLABS_API_KEY`. Speaking replies with
    ElevenLabs also needs `EZO_ELEVENLABS_VOICE_ID` (or per-language
    `EZO_ELEVENLABS_VOICE_ID_UZ/_EN/_RU`, models `EZO_ELEVENLABS_TTS_MODEL_UZ/_EN/_RU`).
    ElevenLabs speaks only the languages in `EZO_ELEVENLABS_TTS_LANGUAGES` (default `en,ru`);
    the others go to OpenAI. Uzbek through ElevenLabs is off until the owner has heard it and
    added `uz` to that list.
  - Screen and photo understanding need `GEMINI_API_KEY`, `OPENAI_API_KEY` or
    `ANTHROPIC_API_KEY`.
  - Without keys, both apps still work for text. They then say clearly that voice or vision
    is not configured on the server.
  - A Claude Pro/Max subscription is **not** an API key.

**EZO's face and languages.** All three apps show EZO's humanoid face and talk in Uzbek,
English and Russian. "Auto" is the default: speak any of the three and EZO answers in the
same language. See [HUMANOID.md](HUMANOID.md).

## 2. Windows app

**Installing:**
1. Download `EZO-Setup-<version>.exe` from the **Devices** workflow artifacts
   (`ezo-windows`) on GitHub.
2. Run it.
   - It is **unsigned** for now, so Windows SmartScreen will warn. Choose "More info → Run
     anyway" only for a build you got from this repository's Actions.
   - It installs per user into `%LOCALAPPDATA%\Programs\EZO`.

**Using:**
- A small pill appears at the top of the screen. Press **Ctrl+Alt+Space**, speak, then
  press it again. EZO answers in text and, if the server has a voice provider, aloud.
- Click **⌨** to type instead of speaking.
- Click **⚙** to open the settings: server URL, token (stored encrypted by Windows),
  permissions and allowed folders.

**Every action is off until you enable it in ⚙:**

| Say | Needs |
|---|---|
| "Kalkulyatorni och", "Bloknotni och" | That app enabled |
| "Ovozni balandlat / pasaytir / o‘chir" | Volume permission |
| "Hisobot faylini top", then "birinchisini och" | At least one allowed folder. EZO searches file **names** only, inside those folders. |
| "Yoz: Salom, ertaga uchrashamiz." | Typing permission. Click into the target app first; EZO pastes into the focused window and restores your clipboard. |
| "Ekranimni tushuntir" | Screen permission. EZO **asks every time** before sending one screenshot to the server; nothing is stored. |
| Anything else | A normal EZO conversation. It is saved on the server and visible on the phone. |

EZO never runs commands it receives from the AI model. It only runs the fixed actions
listed above, and only from your own words.

**Building it yourself:**
- On any OS: `pnpm --filter @ezo/desktop test`.
- On Windows: `pnpm --filter @ezo/desktop dist:win`. The output is
  `apps/desktop/release/EZO-Setup-*.exe`.

## 3. Android app

**Installing:**
1. Download `EZO-debug.apk` from the **Devices** workflow artifacts (`ezo-android`).
2. Allow "install unknown apps" for your browser or file manager, then open the APK.
3. Open EZO → **Sozlamalar** → enter the server URL and token → **Saqlash va ulanish**.

**Using:**
- **🎤:** opens EZO's full-screen face. Speak Uzbek, English or Russian, then tap ■.
  - Android asks for the microphone the first time.
  - EZO answers in your language, in text and aloud.
  - **Auto/UZ/EN/RU** at the top pins a language if needed.
- **📷:** take or choose a photo. EZO explains it. The photo is not stored.
- **📄:** pick a TXT, MD or CSV file and EZO summarises it. **PDF and DOCX are not supported
  yet:** they need EZO's isolated document executor (separate host, PR #33).
- **Suhbat list:** shows conversations from the desktop and the web, and continues them.
- **Loyihalar / Xotira:** the same projects and memories as on the web.
- **Eslatma:** a local reminder notification. Android asks for notification permission.

**Building it yourself** (JDK 21 + Android SDK):
`cd apps/mobile && EZO_ANDROID_ALLOW_LAN_HTTP=1 pnpm apk:debug`.

## 4. iOS — honest plan (not built)

- No iOS build exists yet.
  - Building and signing need macOS with Xcode and an Apple Developer account ($99/year,
    the owner's decision).
  - Testing needs TestFlight or a registered device.
- The same Capacitor code can target iOS with `npx cap add ios` on a Mac.
- **What iOS will allow:**
  - Microphone use while the app is open.
  - Camera and photos.
  - The document picker.
  - Local notifications.
  - Siri Shortcuts / App Intents to open EZO by voice (future work).
- **What iOS does not allow any app to do:**
  - Listening in the background for a wake word.
  - Controlling other apps.
  - Reading other apps' screens.
  - Typing into other apps.
- "Control my phone" features will therefore be Android-only. Even on Android they need
  explicit Accessibility-service consent, which is not implemented.

## 5. Security notes

| Area | Desktop | Mobile |
|---|---|---|
| Token | Encrypted with Windows DPAPI (Electron `safeStorage`); never sent to the UI | Stored in the Android Keystore through secure storage |
| Windows / WebView | Sandboxed and context-isolated, with a CSP; navigation and pop-ups are blocked; only the pill may request the microphone (audio only) | App backups are disabled; plain HTTP is allowed only in debug builds |
| Audio, screenshots, photos | Processed in memory by the API and never stored | Same |

**Revoking access:**
- Desktop: turn the permission off in ⚙, or remove the folder there.
- Phone: Android Settings → Apps → EZO → Permissions.
