# EZO — real-world acceptance (owner scenarios A–J)

Rule: a scenario is **COMPLETE** only with evidence from the real dependency
(the owner's PC/phone, a live provider, a real Telegram chat). CI virtual machines,
emulators and protocol doubles are recorded as what they are. Statuses:
COMPLETE / PARTIAL / BLOCKED / NOT STARTED.

| # | Scenario | Status | Evidence so far | What is missing (and who) |
|---|---|---|---|---|
| A | Install on Windows, floating humanoid, text chat | PARTIAL | Unsigned NSIS installer built and silently installed on GitHub `windows-latest`; installed app self-test passes (Devices runs on #41/#42/#43). Chat works against a real local API (desktop live test). | Install on the owner's PC (owner) |
| B | Uzbek voice → spoken Uzbek reply via a real provider | BLOCKED | STT/TTS pipeline and the language handling are unit-tested; the API reports `voice_not_configured` honestly | Microphone + speakers + `OPENAI_API_KEY` or `ELEVENLABS_API_KEY` (owner) |
| C | Authorise a folder, find and open a file | PARTIAL | Verified on the Windows CI VM: a decoy outside the folder is not returned; Explorer opens the file | Owner PC run |
| D | Upload a real document → grounded answer with the right source | PARTIAL | Text and legacy uploads with checked citations (API tests); isolated PDF/DOCX/EPUB/OCR pass 38/38 real-container tests in CI (PR #33); scanned upload → OCR → index → cited answer runs in the real container (mock model) | Executor host + AI key for a live answer (owner) |
| E | Request a real DOCX/XLSX/PPTX/PDF | PARTIAL | Chat creation works in production mode (PR #39); generated DOCX/XLSX/PPTX open in real LibreOffice with their content (PR #46) | Owner opens files in their own Office/Word |
| F | Install the APK, sign in, same conversation history | PARTIAL | Debug APK built. Emulator run: install, connect to a real API in token mode, open a desktop-started conversation, send from the phone (PR #42; result recorded in that run) | Owner's physical phone |
| G | IELTS practice with evidence-based feedback | PARTIAL | Exact transcript metrics per part, labelled heuristics, null bands (PR #32); chosen cue card (PR #39); server STT + measured speech time (PR #45) | Voice key + microphone for spoken practice |
| H | Permitted browser capability with verified results | PARTIAL | Extension loads in Chromium with `activeTab`/`scripting`/`storage` only; click → preview → confirm → `/api/chat` summary (PR #43) | A toolbar-click round trip on the owner's Chrome with an AI key |
| I | JARVIS authorised document workflow: approval, success, failure, cancel | PARTIAL | Full engine over HTTP with real Ed25519 device keys, hash-bound approvals, rejection, cancellation, failure and retry rules (PR #41, 1282 API tests + Playwright pairing in Chromium) | Owner PC paired; executor host for PDF/DOCX inputs |
| J | Downloads → PDF → percentages → Telegram to "Baxtiyor" | BLOCKED | Every step implemented; Telegram contract verified with a wire double; "delivered" only with Telegram's `message_id` | Paired owner PC + `EZO_TELEGRAM_BOT_TOKEN` + Baxtiyor pressing Start + executor host (owner) |

Owner test script: `EZO_REMAINING_EXTERNAL_APPROVALS.md` §G.
