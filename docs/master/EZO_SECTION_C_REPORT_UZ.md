# EZO — C bo‘lim: haqiqiy idrok (kamera/qo‘l/qarsak) + premium ovoz — egasi uchun hisobot

Sana: 2026-10-27. Tarmoq: `section-c/perception-voice` (B bo‘lim `section-b/humanoid-product`
ustiga, Codex’ning `feat/humanoid-perception` birlashtirilgan). PR: https://github.com/UmidjanDeveloper/EZO/pull/57. Yakuniy head va CI run ID’lari PR’ning oxirgi hisobot izohida (bu fayl head’dan oldin yoziladi).

Hech narsa birlashtirilmadi, joylanmadi, hech qanday xizmat sotib olinmadi, hech qanday
kalit yaratilmadi.

## 1. Egasi nimani yuklab oladi

GitHub → PR → Checks → **Devices** → Artifacts:
- `ezo-windows` → `EZO-Setup-0.1.0.exe` (imzosiz NSIS o‘rnatuvchi; ichida MediaPipe
  modellari va WASM, SHA256 bilan tekshirilgan) + `selftest.json`, `install.txt`.
- `ezo-android` → `EZO-0.1.0-debug.apk` (debug imzo; ichida o‘sha modellar).
- `ezo-android-emulator` → emulyator hisoboti va skrinshotlar (SIMULYATSIYA).

Sinov ro‘yxati: `docs/master/EZO_OWNER_TEST_UZ.md` (10 daqiqa, uch platforma, Diagnostika
hisobotini nusxalab qaytarish).

## 2. Simulyatsiyada nima ishlaydi (CI, soxta kamera va soxta mikrofon fayli)

- **Bitta diqqat dvigateli**: Codex’ning `AttentionController` yagona holat mashinasi;
  avatar tomonidagi `AttentionDriver` o‘chirildi, o‘rniga yupqa `MotionAdapter`
  (dvigatel niyatini figuraga qo‘llaydi, sichqoncha/barmoq zaxirasini «kamera emas» deb
  belgilaydi, yashirin/to‘xtatilganda nigohni qo‘yib yuboradi). Qaror `docs/devices/HUMANOID.md` da.
- **Haqiqiy dvigatel uchala ilovada**: `scripts/vision-assets.mjs` rasmiy MediaPipe
  modellarini (face/hand landmarker) build vaqtida yuklab, SHA256 va hajmini
  `scripts/vision/pins.json` ga solishtiradi (nomuvofiq bo‘lsa rad etadi), pin qilingan WASM’ni
  `node_modules` dan nusxalaydi, dvigatel worker’ini bundle qiladi. Ish vaqtida CDN yo‘q.
  Worker har bir baytni yana tekshiradi. Veb: `public/vision`; Windows: `dist/vision`
  (`https://ezo.desktop` origin’idan beriladi, CSP qat’iy: `wasm-unsafe-eval`, `worker-src 'self' blob:`,
  `connect-src 'self' blob:` — oxirgisi bo‘lmasa WASM runtime tekshirilgan blob’ni o‘qiy olmaydi);
  Android: `dist/vision`, manifestda `CAMERA` ruxsati.
- **Kamera tugmasi** faqat `vision-assets.json` tekshiruvdan o‘tganda yoqiladi; aks holda
  aniq sabab bilan o‘chiq («model yo‘q», «tekshiruvdan o‘tmadi», «tarmoq»).
- **Playwright «perception» loyihasi** (Chromium soxta kamera + qarsak-ga o‘xshash
  portlashlar yozilgan soxta mikrofon fayli): veb sahnasi — modellar tekshirildi, worker
  inference qiladi (fps > 0), holat halol («yuz topilmadi» — soxta kadrda yuz yo‘q),
  3 marta ochib-yopish, yashirin tab → kamera darhol o‘chadi; **qarsak** → «Qarsak eshitildi»
  → haqiqiy `/api/voice/speak` yo‘li (mock) → «Eshitaman seni.» ijro etildi (jag‘ o‘lchangan
  ovoz bilan) → ikkinchi qarsak keshdan, qayta sintez yo‘q; provayder yo‘q → «javob
  aytilmadi» (hech qachon «ijro etildi» deb aldamaydi). Windows pill (dist xotiradan) va
  Android ilovasi (dist) ham o‘sha dvigatel bilan: 6/6 o‘tdi (mahalliy, to‘liq Playwright 94/94 bilan birga); skrinshotlar `docs/devices/img/section-c-simulation-*.jpg`.
- **Emulyator** (Devices): haqiqiy APK, `CAMERA` berilgan, sahnada kamera tugmasi bosiladi,
  worker emulyator sahnasida inference qiladi: ce27a47 da **o‘tdi** (holat «yuz topilmadi»,
  1 kadr/s, inference ≈1,2 s, dvigatel ≈17 s da tayyor), 55c489e va 7776d42 da esa 15 s
  muddatga ulgurmadi (23 s) — shuning uchun init muddati sukut bo‘yicha 60 s qilindi (5-band).
- **ElevenLabs**: til bo‘yicha ovoz/model (`EZO_ELEVENLABS_VOICE_ID_UZ/_EN/_RU`,
  `EZO_ELEVENLABS_TTS_MODEL_UZ/_EN/_RU`), tasdiqlangan tillar uchun ElevenLabs, qolganlari
  uchun OpenAI (ElevenLabs’ga HTTP so‘rov yuborilmaydi); o‘zbekcha sukut bo‘yicha o‘chiq.
  Mock HTTP testlari: uz/en/ru, fallback, mavjud emas yo‘li — 850 o‘tdi, 10 o‘tkazib yuborildi (ruff, ruff format, mypy toza).

## 3. Faqat egasi tasdiqlaydi (KUTILMOQDA)

- Haqiqiy kamerada yuz va qo‘l (chap/o‘ng), haqiqiy qarsak, haqiqiy telefon, haqiqiy
  ovozlar (uz/en/ru), ElevenLabs o‘zbekcha sifati. Ro‘yxat: `docs/master/EZO_OWNER_TEST_UZ.md`.
- Model litsenziyasi: MediaPipe model kartalarida Apache-2.0 deyilgan; bu sessiyada
  sahifa ochilmadi (tarmoq) — `scripts/vision/MODEL_LICENSE_REVIEW.txt` da tasdiq katagi.

## 4. Server muhit o‘zgaruvchilari (faqat nomlar)

`OPENAI_API_KEY`, `ELEVENLABS_API_KEY`, `EZO_VOICE_PROVIDERS`, `EZO_ELEVENLABS_VOICE_ID`,
`EZO_ELEVENLABS_VOICE_ID_UZ`, `EZO_ELEVENLABS_VOICE_ID_EN`, `EZO_ELEVENLABS_VOICE_ID_RU`,
`EZO_ELEVENLABS_TTS_MODEL`, `EZO_ELEVENLABS_TTS_MODEL_UZ`, `EZO_ELEVENLABS_TTS_MODEL_EN`,
`EZO_ELEVENLABS_TTS_MODEL_RU`, `EZO_ELEVENLABS_TTS_LANGUAGES` (o‘zbekcha uchun `en,ru,uz`),
`EZO_ELEVENLABS_STT_MODEL`. Namuna: `deploy/full-owner.env.example`.

## 5. Codex’ga so‘rov (`packages/face-tracking`, men tahrir qilmadim)

1. `PerceptionOptions` ga `workerFactory?: () => Worker` (yoki `workerUrl`) qo‘shing —
   `HumanoidPerception` `new Worker(new URL('./vision.worker.ts', import.meta.url))` ni
   qattiq kodlaydi; esbuild (Windows) uni bundle qila olmaydi, Turbopack (veb) esa o‘sha
   kirishni bundle qilmoqchi bo‘lib to‘xtab qoladi. Hozircha `@ezo/perception-client`
   dvigatelning qismlarini o‘zi tarkiblaydi (xuddi `HumanoidPerception` kabi) va vebda alias ishlatiladi.
2. `validateAssets` da `https?:` dan tashqari ilova sxemasiga (masalan `ezo://app`) ruxsat
   bering — Windows ilovasi shu sababli `https://ezo.desktop` ni mahalliy protokol
   handler orqali «soxta» qilishga majbur.
3. `ClapMicrophone` uchun mikrofon darajasi (`onLevel`) — Diagnostikada «mic level» ko‘rsatish uchun.
4. `onStatus` xato matnlarini mashina o‘qiydigan kodga ajrating (`denied`, `revoked`,
   `interrupted`) — hozir UI regex bilan farqlaydi.
5. **Ko‘rib chiqing:** `createVisionEstimator` da init (sukut 60 s) va kadr (15 s) muddatlari
   ajratildi, `initTimeoutMs`/`frameTimeoutMs` bilan sozlanadi, 1–120 s chegara, 3 test — bu
   #57 dagi `packages/face-tracking` ga yagona o‘zgarish, #58 birlashgandan keyin qilindi
   (ikki Claude sessiyasi bir xil tuzatishni kiritgan edi, bittaga birlashtirildi). Sabab: CI
   Android emulyatori dvigatelni 17–23 s da ishga tushiradi, 15 s muddat uni ikki marta uzdi.
6. `MEDIAPIPE_ASSET_PINS` ga SIMD WASM variantini ham qo‘shing (hozir faqat `nosimd`
   pin qilingan): zamonaviy telefon va kompyuterlarda inference 2–4 barobar tezlashadi.

## 6. Raqamlar

| Nima | Natija |
|---|---|
| `packages/avatar` | 25/25 |
| `packages/face-tracking` (Codex, o‘zgartirilmagan) | 51/51 |
| `packages/perception-client` | 3/3 |
| `apps/web` (lint, tsc, vitest) | 97/97 |
| `apps/desktop` (vitest, tsc, build) | 69/69 (+2 o‘tkazib yuborilgan) |
| `apps/mobile` (vitest, tsc, build, `cap sync`) | 19/19 |
| API (ruff, mypy, pytest) | 850 o‘tdi, 10 o‘tkazib yuborildi |
| Playwright (to‘liq, `perception` loyihasi bilan) | 94/94, 6.2 daqiqa |
| Vision assets | face 3 758 596 B, hand 7 819 105 B, WASM 10 647 962 B — SHA256 mos |

Topilgan va tuzatilgan xato: `connect-src` da `blob:` yo‘qligi sababli worker uchala
mijozda start paytida o‘lardi (CSP). Topilmagan bo‘lsa, egasida kamera tugmasi doim
«xato» ko‘rsatardi — simulyatsiya shu uchun kerak edi.

«Tirik humanoid tayyor» deyilmaydi: ko‘z/qo‘l/kamera va jismoniy ovoz testlari egasi
tomonidan o‘tkazilmagan. «100% xatosiz» yoki «fotorealistik» da’volar yo‘q.
