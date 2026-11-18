# EZO — egasi uchun 10 daqiqalik sinov (Windows + Android + veb)

Bu ro‘yxat **haqiqiy** mikrofon, dinamik va telefon bilan bajariladi. Kamera ishlatilmaydi (yuz/qo‘l kuzatuvi koddan olib tashlangan). CI’dagi
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
| A3 | Sozlamalar → «Mikrofon» → «Qarsakni tinglash» ni yoqing. | Katak belgilandi. | — |
| A4 | Pill’dagi `⤢` ni bosing → sahna ochiladi. Sichqonchani humanoid ustida yurgizing. | Katta humanoid; bosh sichqonchaga qarab buriladi. | — |
| A6 | «Qarsakni tinglash» → bir marta qarsak chaling. | «Qarsak eshitildi ×1», EZO «Eshitaman seni.» deb aytadi (jag‘ ovoz bilan qimirlaydi), keyin tinch turadi. | «Ovoz provayderi yo‘q» — serverda kalit yo‘q. Qarsak eshitilmasa — mikrofon darajasi, 1–2 m masofa. |
| A7 | Sozlamalar → Ilova tili: English → qarsak; Русский → qarsak. | «I'm listening.» / «Я тебя слушаю.» aytiladi (ikkinchi marta darhol — kesh). | — |
| A8 | Ctrl+Alt+H (yashirish) → qayta ko‘rsatish. | Mikrofon o‘chadi (MIC belgisi yo‘qoladi), o‘zi qayta yoqilmaydi. | — |
| A9 | Sozlamalar → pastdagi **Diagnostika** → «Hisobotni nusxalash». | Buferda matn: fps, clap soni, TTS provayder, versiya, sha. | «Yangilash»ni bosing; sahna ochiq bo‘lsin. |

## B. Android (4 daqiqa)

| # | Qadam | Kutilgan natija | Agar ishlamasa |
|---|---|---|---|
| B1 | `EZO-0.1.0-debug.apk` ni o‘rnating («Noma’lum manbalar»ga ruxsat). | Xush kelibsiz sahifasi, humanoid bosh. | — |
| B2 | Server manzili (LAN: `http://192.168.x.x:8000`) + token → «Saqlash va ulanish». | Yashil nuqta. | Telefon va server bir Wi‑Fi’da bo‘lsin; serverda `EZO_CORS_ORIGINS` da `https://localhost` bo‘lsin. |
| B3 | Chat → 🎤 → sahna ochiladi. Barmog‘ingizni humanoid ustida yurgizing. | Humanoid; bosh barmoqqa qarab buriladi. | — |
| B4 | «Qarsakni tinglash» → qarsak. | «Qarsak eshitildi», «Eshitaman seni.» aytiladi. | B6 dagi hisobot. |
| B5 | Ilovani fonga oling (Home) → qaytib keling. | Qarsak mikrofoni o‘chgan, o‘zi yoqilmaydi. | — |
| B6 | Ko‘proq → **Diagnostika** → «Hisobotni nusxalash». | Buferda matn (fps, kadr vaqti, xotira ham). | — |
| B7 | Telefon sozlamalarida EZO uchun **Mikrofon** ruxsatini o‘chiring → sahna → «Qarsakni tinglash». | «Ruxsat berilmadi» holati, ilova yopilib qolmaydi. | Ilova yopilib qolsa — B6 hisobotini yuboring. |

## C. Veb (2 daqiqa)

| # | Qadam | Kutilgan natija |
|---|---|---|
| C1 | Brauzerda EZO → «Gaplashish». Sichqonchani humanoid ustida yurgizing. | Humanoid sichqonchaga qaraydi; sahnada kamera yo‘q. |
| C2 | «Qarsakni tinglash» → qarsak. | «Qarsak eshitildi», javob aytiladi. |
| C3 | Tabni almashtiring → qaytib keling. | Qarsak mikrofoni o‘chgan, o‘zi yoqilmaydi. |
| C4 | Sahnada pastdagi **Diagnostika** → «Hisobotni nusxalash». | Buferda matn: versiya, sha, fps, mikrofon, TTS provayder. |

### Ixtiyoriy: ovoz aniqligi (server kalitlari bilan)

Serverda `OPENAI_API_KEY` va/yoki `ELEVENLABS_API_KEY` bo‘lsa, kompyuterda:
`python scripts/voice_phrase_check.py --api http://<server> --token <token>` — 15 ta jumla
(uz/en/ru) sintez qilinadi, qayta tanib olinadi, har biri uchun WER/CER chiqadi. Bu faqat
«tanib olish aniqligi»; ovoz tabiiyligini o‘zingiz eshitib baholaysiz (D bo‘limi).

## D. Natijani qaytaring

Claude’ga shuni tashlang (3 ta hisobot + 3 ta javob):

```
Windows diagnostika: <A9 matni>
Android diagnostika: <B6 matni>
Veb: C1 ✓/✗, C2 ✓/✗, C3 ✓/✗
Eshitgan ovozim: uz ✓/✗ (tabiiymi? 1–5), en ✓/✗, ru ✓/✗
Ishlamagan qadamlar: A?, B? — nima ko‘rindi
```

Hisobotda rasm yoki ovoz yozuvi yo‘q — faqat raqamlar va so‘zlar.

## Tarjimon rejimi (2026-10-29)

Chap paneldagi alohida tarjima sahifasi olib tashlandi (egasi qarori). Tarjima endi ovozli
rejimning o‘zida, ikki odam o‘rtasida ishlaydi:

1. «Gaplashish» → robotga bosing → **«EZO, menga tarjimon bo‘lib ber»** deng.
   Kutilgan natija: EZO «Tarjimon rejimi yoqildi…» deydi, tepada «Tarjimon: UZ ⇄ EN» chiqadi.
   Boshqa juftlik: «rus tili bilan o‘zbek tili o‘rtasida tarjimon bo‘l».
2. Navbat bilan gapiring: o‘zbekcha gap inglizchaga, inglizcha gap o‘zbekchaga tarjima
   qilinib, ovoz chiqarib o‘qiladi. Kim gapirishini tepadagi UZ/EN tugmasi bilan ham tanlash mumkin.
3. To‘xtatish: **«tarjimon rejimini to‘xtat»** deng yoki «Tarjimonni to‘xtatish» tugmasini bosing.

Agar ishlamasa: tarjima AI provayder kalitiga muhtoj (`GEMINI_API_KEY`, AI Studio’dan
`AIza…` bilan boshlanadigan kalit). Kalitsiz «Tarjima bo‘lmadi» xabari chiqadi.
Bu navbatma-navbat (turn-based) tarjima; bir vaqtda (sinxron) tarjima emas.

## Hamma narsa joyidami? — bitta buyruq (2026-11-18)

EZO ishlamayotgandek tuyulsa, avval shuni ishga tushiring (loyiha papkasida, EZO ishlab turganda):

```powershell
docker compose exec api python -m ezo_api.doctor
```

U o‘zbekcha aytadi:
- `.env` dagi AI kalitlari API ga yetib bordimi (faqat uzunligi, kalitning o‘zi chiqmaydi);
- kalit to‘g‘ri ko‘rinishdami (Gemini `AIza…`, OpenAI `sk-…`);
- har bir provayder kalitni qabul qildimi (bitta juda kichik haqiqiy so‘rov; o‘tkazib yuborish: `--no-probe`);
- o‘zbekcha server ovozi yoqilganmi, OCR va Office→PDF bormi.

Xuddi shu tekshiruv brauzerda ham bor: **Sozlamalar → Kalitlarni tekshirish**. Kalit rad etilsa,
chat tepasida qizil ogohlantirish ham chiqadi. `.env` o‘zgarsa:
`docker compose up -d --force-recreate api`.
## PDF, DOCX, EPUB va skan qilingan hujjatlarni o‘qish (2026-11-18)

Egasi ruxsati bilan (2026-11-18) hujjatlar faqat **sizning kompyuteringizda** shunday yoqiladi:

1. `.env` faylining oxiriga bitta qator qo‘shing:
   ```
   COMPOSE_PROFILES=documents
   ```
2. Loyiha papkasida:
   ```powershell
   docker compose up -d --build
   ```
   Birinchi marta OCR (Tesseract) va LibreOffice o‘rnatiladigan hujjat obrazi yig‘iladi —
   bir necha daqiqa ketadi.
3. Chatga PDF/DOCX/EPUB/rasm tashlang (5 MB gacha). Fayl yonida avval «navbatda», keyin
   «indekslandi» chiqadi; shundan keyin EZO hujjat bo‘yicha javob beradi.

Qanday ishlaydi: `document-worker` har bir faylni alohida, qulflangan konteynerda ochadi
(internetsiz, faqat o‘qish, 768 MB xotira, 64 jarayon, 25 soniya, hech qanday huquqsiz).
Buning uchun ishchi Docker’ni boshqara oladi (`/var/run/docker.sock`) — shuning uchun bu
profil faqat shaxsiy kompyuter uchun; umumiy serverda hujjat ishchisi alohida hostda turadi
(`docs/deployment/EXECUTOR_REQUIREMENTS.md`). API’ning o‘zi Docker’ga hech qachon ulanmaydi.

Agar ishlamasa: `docker compose logs document-worker` — xato shu yerda ko‘rinadi.
Profil yoqilmagan bo‘lsa, chatda «PDF/DOCX/skan o‘qish yoqilmagan…» degan aniq xabar chiqadi.

## Dasturchi agent, ko‘p tilli imtihonchi va kutubxona o‘rganish (2026-11-18)

**Sayt yoki dastur tuzish.** Chatga oddiy so‘z bilan yozing:

- «Menga kafe uchun website tuzib ber»
- «Python’da kalkulyator dasturi yozib ber»
- «Telegram bot yozib ber, ob-havoni aytsin»

EZO loyihaning barcha fayllarini yozadi (README’da ishga tushirish qadamlari bilan) va
ularni ZIP qilib saqlaydi — javob ostida karta chiqadi. Sayt bo‘lsa, kartada yana
**«Sayt (bitta HTML fayl)»** bor: yuklab oling va brauzerda oching — to‘liq ishlaydi.
«Yaratilganlar» sahifasida saytning ko‘rinishi va fayllar ro‘yxati chiqadi (bu oynada
sayt skriptlari xavfsizlik uchun ishlamaydi).

O‘zgartirish uchun shu suhbatda yozing: «tugmani ko‘k rangga o‘zgartir», «kontakt sahifasini
qo‘sh» — EZO shu loyihaning yangi versiyasini saqlaydi (eski versiya qoladi). EZO kodni
o‘zi ishga tushirmaydi: xato chiqsa, xato matnini yuboring.

**Til imtihonchisi.** «Rus tilidan imtihon ol», «nemis tili bo‘yicha meni sinab ko‘r»,
«ingliz tilidan examiner bo‘l», «test my French». Imtihon 3 qismdan iborat (suhbat,
tasvirlash, muhokama; ~6 savol), oxirida CEFR darajasi (A1–C2), xatolar va tavsiyalar
bilan hisobot fayli chiqadi. «tugat» desangiz, erta yakunlanadi. Tillar: ingliz, rus,
nemis, fransuz, ispan, italyan, turk, arab, koreys, xitoy, yapon, qozoq, portugal,
o‘zbek. Bu simulyator: rasmiy imtihon yoki sertifikat emas.

**Kutubxonani o‘rganish.** Endi havola shart emas: «fastapi kutubxonasini o‘rgan»,
«npm axios paketini o‘rgan», «pallets/flask repozitoriyasini o‘rgan». EZO hujjatlarni
o‘qib, bilim kutubxonasiga qo‘shadi va keyingi savollarda shundan foydalanadi
(«Bilim» sahifasida holati ko‘rinadi). Hech narsa o‘rnatilmaydi va ishga tushirilmaydi.
