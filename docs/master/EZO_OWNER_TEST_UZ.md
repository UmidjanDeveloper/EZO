# EZO — egasi uchun 10 daqiqalik sinov (Windows + Android + veb)

Bu ro‘yxat **haqiqiy** kamera, mikrofon, dinamik va telefon bilan bajariladi. CI’dagi
hamma narsa simulyatsiya; faqat siz quyidagilarni tasdiqlay olasiz. Har bir qadamda
«kutilgan natija» va «agar ishlamasa» bor. Oxirida Diagnostika hisobotini nusxalab
Claude’ga tashlang — shu bilan «yana bir prompt» sikli tugaydi.

Tayyorgarlik (5 daqiqa, bir marta):
- Serveringizda (`.env`) ovoz uchun kalit bo‘lsin: `OPENAI_API_KEY` (o‘zbekcha ham
  gapiradi) yoki/va `ELEVENLABS_API_KEY` + `EZO_ELEVENLABS_VOICE_ID` (en/ru). O‘zbekcha
  ElevenLabs — faqat siz eshitib tasdiqlagandan keyin (`EZO_ELEVENLABS_TTS_LANGUAGES=en,ru,uz`,
  `EZO_ELEVENLABS_TTS_MODEL_UZ=eleven_v3`, `EZO_ELEVENLABS_VOICE_ID_UZ=...`).
- Artefaktlarni yuklab oling: GitHub → PR → «Checks» → **Devices** ishga tushishi →
  «Artifacts»: `ezo-windows` (ichida `EZO-Setup-0.1.0.exe`) va `ezo-android`
  (ichida `EZO-0.1.0-debug.apk`).

## A. Windows (4 daqiqa)

| # | Qadam | Kutilgan natija | Agar ishlamasa |
|---|---|---|---|
| A1 | `EZO-Setup-0.1.0.exe` ni ishga tushiring (SmartScreen: «Batafsil → Baribir ishga tushirish»). | O‘rnatildi, yuqorida doiracha (pill) chiqdi, Sozlamalar oynasi xush kelibsiz bilan ochildi. | Antivirus bloklasa — imzosiz build; sertifikat kelguncha ruxsat bering. |
| A2 | Sozlamalar → server manzili + token → «Ulanishni tekshirish». | Yashil nuqta, «Server ulangan, AI tayyor». | Qizil: manzil/tokenni tekshiring; `/api/health` brauzerda ochiladimi? |
| A3 | Sozlamalar → «Mikrofon va kamera» → **Kamera** ni yoqing; «Qarsakni tinglash» ni yoqing. | Ikkala katak belgilandi. | — |
| A4 | Pill’dagi `⤢` ni bosing → sahna ochiladi → «Kamerani yoqish». Windows ruxsat so‘rasa — «Ruxsat». | «Kamera: yuz ko‘rinmoqda», CAM belgisi, EZO sizga qaraydi; yuzni chapga/o‘ngga bursangiz — bosh ergashadi. | «Kamera xatosi» matnini Diagnostikaga yozing. «Kamera modeli yo‘q» chiqsa — build’da vision assets yo‘q (CI logi). |
| A5 | Qo‘lingizni ko‘tarib chapga-o‘ngga harakatlantiring. | «EZO qo‘lingizga qaraydi»; ko‘zlar oldin, bosh keyin buriladi. | Qo‘l ko‘rinmasa — yorug‘lik, qo‘l kameradan 0.5–1 m. |
| A6 | «Qarsakni tinglash» → bir marta qarsak chaling. | «Qarsak eshitildi ×1», EZO «Eshitaman seni.» deb aytadi (jag‘ ovoz bilan qimirlaydi), keyin tinch turadi. | «Ovoz provayderi yo‘q» — serverda kalit yo‘q. Qarsak eshitilmasa — mikrofon darajasi, 1–2 m masofa. |
| A7 | Sozlamalar → Ilova tili: English → qarsak; Русский → qarsak. | «I'm listening.» / «Я тебя слушаю.» aytiladi (ikkinchi marta darhol — kesh). | — |
| A8 | Ctrl+Alt+H (yashirish) → qayta ko‘rsatish. | Kamera va mikrofon o‘chadi (CAM/MIC belgilari yo‘qoladi), o‘zi qayta yoqilmaydi. | — |
| A9 | Sozlamalar → pastdagi **Diagnostika** → «Hisobotni nusxalash». | Buferda matn: fps, inference ms, clap soni, TTS provayder, versiya, sha. | «Yangilash»ni bosing; sahna ochiq bo‘lsin. |

## B. Android (4 daqiqa)

| # | Qadam | Kutilgan natija | Agar ishlamasa |
|---|---|---|---|
| B1 | `EZO-0.1.0-debug.apk` ni o‘rnating («Noma’lum manbalar»ga ruxsat). | Xush kelibsiz sahifasi, humanoid bosh. | — |
| B2 | Server manzili (LAN: `http://192.168.x.x:8000`) + token → «Saqlash va ulanish». | Yashil nuqta. | Telefon va server bir Wi‑Fi’da bo‘lsin; serverda `EZO_CORS_ORIGINS` da `https://localhost` bo‘lsin. |
| B3 | Chat → 🎤 → sahna → «Kamerani yoqish» → Android ruxsat → «Ruxsat». | «Kamera: yuz ko‘rinmoqda», EZO sizga qaraydi, bosh/qo‘l harakatiga ergashadi. | «Kamera xatosi: …» matnini yozing. Ruxsat rad etilsa — Android sozlamalari → EZO → Ruxsatlar. |
| B4 | «Qarsakni tinglash» → qarsak. | «Qarsak eshitildi», «Eshitaman seni.» aytiladi. | B6 dagi hisobot. |
| B5 | Ilovani fonga oling (Home) → qaytib keling. | Kamera va mikrofon o‘chgan, o‘zi yoqilmaydi. | — |
| B6 | Ko‘proq → **Diagnostika** → «Hisobotni nusxalash». | Buferda matn. | — |

## C. Veb (2 daqiqa)

| # | Qadam | Kutilgan natija |
|---|---|---|
| C1 | Brauzerda EZO → «Gaplashish» → «Kamerani yoqish» → ruxsat. | «Kamera: yuz ko‘rinmoqda», EZO sizga qaraydi. |
| C2 | «Qarsakni tinglash» → qarsak. | «Qarsak eshitildi», javob aytiladi. |
| C3 | Tabni almashtiring → qaytib keling. | Kamera o‘chgan, o‘zi yoqilmaydi. |

## D. Natijani qaytaring

Claude’ga shuni tashlang (3 ta hisobot + 3 ta javob):

```
Windows diagnostika: <A9 matni>
Android diagnostika: <B6 matni>
Veb: C1 ✓/✗, C2 ✓/✗, C3 ✓/✗
Eshitgan ovozim: uz ✓/✗ (tabiiymi? 1–5), en ✓/✗, ru ✓/✗
Ishlamagan qadamlar: A?, B? — nima ko‘rindi
```

Hisobotda rasm, ovoz yozuvi yoki yuz nuqtalari yo‘q — faqat raqamlar va so‘zlar.

Sahna qanday ko‘rinishi kerak (CI dagi SIMULYATSIYA — soxta kamera, yuz yo‘q, shuning uchun
«yuz topilmadi»): `docs/devices/img/section-c-simulation-web-stage.jpg`,
`…-windows-pill-stage.jpg` (qarsakdan keyin gapirmoqda), `…-android-stage.jpg`. Sizda haqiqiy
kamera oldida «Kamera: yuz ko‘rinmoqda» bo‘lishi kerak.
