# EZO — remaining owner actions and external approvals

Everything here needs the owner: a credential, a device, an account, money, or a
decision. Code-side work for each item is listed with its PR. **One approval covers only
the action it names**; nothing here is pre-authorized.

## A. Review and merge decisions (owner)

| PR | What | Why it needs you |
|---|---|---|
| [#39](https://github.com/UmidjanDeveloper/EZO/pull/39) | Audit F18–F25 (memory recall consent, honest chat files, CSRF guard, quotas) | Changes consent semantics: memories saved without consent are no longer recalled unless recall is turned on. Needs independent review |
| [#41](https://github.com/UmidjanDeveloper/EZO/pull/41) | JARVIS governed task engine | Device auth, approvals and external effects: needs independent security review |
| [#42](https://github.com/UmidjanDeveloper/EZO/pull/42) | Android emulator acceptance in CI | CI-only change |
| [#43](https://github.com/UmidjanDeveloper/EZO/pull/43) | Chrome extension summary/explanation | Adds the `storage` permission and page-text sending after confirmation |
| [#44](https://github.com/UmidjanDeveloper/EZO/pull/44) | Mobile PDF/DOCX via Student | Depends on the executor host for live results |
| [#45](https://github.com/UmidjanDeveloper/EZO/pull/45) | IELTS server speech recognition + examiner voice | Live quality needs your microphone and a voice key |
| [#46](https://github.com/UmidjanDeveloper/EZO/pull/46) | Generated Office files open in real LibreOffice (CI) | Adds `libreoffice-impress-nogui` to the test-only image stage |
| [#47](https://github.com/UmidjanDeveloper/EZO/pull/47) | Model-planned presentation intake | Changes what the presentation outline is based on |
| [#48](https://github.com/UmidjanDeveloper/EZO/pull/48) | Owner-managed accounts, per-user tokens, tiers, quotas (stacked on #41) | Authentication and authorization change: needs independent security review; merge after #41 |
| [#40](https://github.com/UmidjanDeveloper/EZO/pull/40) | Mission state + release documents | Docs |
| #36 | Dependabot Python bumps | Not reviewed by this mission; decide separately |

Suggested merge order: #37 → #39 → #41 → #42/#43/#44/#45 → #40 (rebase as needed).

## B. Credentials (server `.env` only — never in apps, never in git)

| Credential | Unlocks | Scenario |
|---|---|---|
| `GEMINI_API_KEY` or `OPENAI_API_KEY` (or `ANTHROPIC_API_KEY`) | Real AI replies, screen/photo explanation, Student summaries | A, D, E, G |
| `OPENAI_API_KEY` or `ELEVENLABS_API_KEY` (+ voice id) | Speech-to-text and spoken replies (Uzbek/English/Russian) | B, G |
| `EZO_TELEGRAM_BOT_TOKEN` (from @BotFather) | JARVIS Telegram delivery with real receipts | J |
| `EZO_API_TOKEN` (you generate it) | Token mode for phone/LAN use | F |

The Claude Max/Pro subscriptions do **not** include production API usage; API keys are billed by their providers.

## C. Devices (only the owner has them)

| Device | Needed for |
|---|---|
| Your Windows PC with microphone and speakers | Scenarios A, B, C, I, J live: install, voice, folder search, JARVIS pairing |
| Your Android phone | Scenario F live: install the APK, voice, camera, shared history on real Wi‑Fi |
| A person who presses Start in your EZO Telegram bot (e.g. "Baxtiyor") | Scenario J: a recipient Telegram allows the bot to message |
| Mac + Xcode + Apple Developer account | Any iOS build (currently BLOCKED) |

## D. Infrastructure (paid or account actions — not done, not purchased)

| Action | Why | Status |
|---|---|---|
| Executor host (separate VM with Docker/cgroup v2) running the Student worker and `ezo_api.jarvis.worker` | Live PDF/DOCX/EPUB/OCR reading and Office→PDF; JARVIS document steps | Code ready (PR #33, #41); host not provisioned |
| Primary host / cloud project (Render, Vercel, Supabase or a VPS) | Using EZO away from your PC | P9 preparation docs exist (PR #31); nothing provisioned |
| Backup storage and restore drill | Data durability | Plan only (`docs/deployment/BACKUP_RESTORE_PLAN.md`) |
| Domain + TLS certificate | HTTPS for phone/remote use | Not started |

Budget target: about $10/month infrastructure, excluding AI APIs. Get real, inclusive quotes before buying anything.

## E. Signing and stores

| Item | Needed | Effect until done |
|---|---|---|
| Windows code-signing certificate | Removes the SmartScreen warning; enables trusted auto-update | Unsigned installer; SmartScreen warns |
| Android release keystore (you keep it) | Release APK/AAB, updates over existing installs | Debug-signed test APK only |
| Google Play / Apple developer accounts | Store publication | Not planned without your approval |

## F. Licensing decisions

| Item | Decision needed |
|---|---|
| VoiceStudio (AGPL-3.0, some weights CC-BY-NC) | Whether to run it as a separate service and accept its terms. EZO only speaks its HTTP API; no code is copied |
| APEX-UI components (MIT) | Which visual components to adopt; attribution is kept if used |

## G. Owner test script (after A–C)

1. Install the Windows build (guide: `docs/devices/EZO_WINDOWS_INSTALL_GUIDE_UZ.md`) and run a text chat (A).
2. Turn on the microphone and say "Salom EZO" in Uzbek (B).
3. Allow one folder and say "hisobot faylini top" (C).
4. Upload a PDF in Student, wait for the worker, ask a question (D).
5. Ask in chat: "Oylik xarajatlar uchun excel jadval yarat" and open the file (E).
6. Install the APK and open the same conversation on the phone (F).
7. Practise IELTS in text, then by voice (G).
8. Use the Chrome extension on a news page: "Sahifani qisqacha bayon qil" (H).
9. Pair JARVIS, link a recipient, and run the reference sentence; approve on the PC (I, J).

Report anything that fails; real-hardware failures are the next engineering priority.

## F. Product decisions (only the owner can make them)

| Decision | Current behaviour until you decide |
|---|---|
| Self-signup for other people | Off. Only you create accounts (Super Admin page or `/api/admin/users`) and hand each person a token. |
| Paid tiers and payment provider | No billing. Tiers (free/pro/premium) only change daily limits, and you set them by hand. Limits are in `apps/api/src/ezo_api/account/entitlements.py`. |
| K6 (EZO opening GitHub PRs itself) | BLOCKED by design until K4/K5 exist (`docs/master/EXECUTION_GATES.md`); it would also need a GitHub token you issue. |

Merged so far during this mission: [#37](https://github.com/UmidjanDeveloper/EZO/pull/37) (security recovery).
