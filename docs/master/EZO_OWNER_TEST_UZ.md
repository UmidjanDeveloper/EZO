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

## Tuman markazi: loyihalar, xatlov, ogohlantirishlar (2026-11-18)

Chap menyuda **«Tuman markazi»** sahifasi bor. Bu yerda tumandagi har bir loyiha (masalan,
«Xatlov 2026») uchun kim qancha bajargani, kim orqada qolgani va ogohlantirishlar turadi.

**1. Loyiha qo‘shish.** «Yangi loyiha» → nomi, o‘lchov birligi (xonadon), mas’ul tashkilot,
boshlanish va muddat. Muddat bo‘lsa, EZO bugungacha qancha bajarilishi kerakligini hisoblaydi
va 80% dan kam bajarganlarni «Orqada» deb belgilaydi.

**2. Ma’lumot manbai** (uchtasidan biri):
- **Rasmiy API** — loyiha ichida «Ma’lumot manbai → Rasmiy API»: API manzili (https://…),
  ro‘yxat joyi (masalan `data.items`) va maydonlar (ism, reja, bajarildi, telefon, mahalla, ID).
  Token qiymatini faqat `.env` ga yozing:
  ```
  EZO_DISTRICT_API_TOKEN=...
  ```
  (bir nechta API bo‘lsa: `EZO_DISTRICT_API_TOKEN_BANDLIK=...` va sahifada shu nomni yozasiz).
  EZO API’ni chatda so‘ralganda (10 daqiqada bir martadan ko‘p emas) yoki «API’dan yangilash»
  tugmasi bosilganda o‘qiydi. API hujjatini bersangiz, maydonlarni aniq moslab beraman.
- **Excel/CSV** — ustunlar: F.I.Sh, Telefon, Mahalla, Reja, Bajarildi (lotin, kirill, rus
  sarlavhalari ham tushuniladi).
- **Qo‘lda** — har bir odam uchun reja va bajarilgan sonini kiritish.

**3. Chatda so‘rash.**
- «Xatlov qalay ketyapti?» → umumiy foiz, muddatga nisbatan sur’at, kim orqada qolgani.
- «Nega Aliyev xatlov qilmayapti, uni ogohlantir» → Aliyev uchun ogohlantirish **qoralamasi**.
- «Xatlov bo‘yicha orqada qolganlarni ogohlantir» → har biriga qoralama (20 tagacha).

**4. Yuborish — faqat sizning tasdig‘ingiz bilan.** Qoralama javob ostida karta bo‘lib chiqadi:
matnni tahrirlashingiz mumkin, «Yuborish» bosilib tasdiqlangandagina ketadi. Har bir
kanalning haqiqiy natijasi (SMS id, Telegram xabar raqami yoki xato) kartada va jurnalda
saqlanadi. Bir xabar ikki marta yuborilmaydi. Faqat egasi akkaunti yubora oladi.

**Kanallar** (`.env` da, o‘zingiz yozasiz):
```
# SMS — Eskiz.uz hisobingiz (notify.eskiz.uz)
EZO_ESKIZ_EMAIL=
EZO_ESKIZ_PASSWORD=
EZO_ESKIZ_SENDER=4546
# Telegram — bot tokeni (mas’ullar botga /start bosib, JARVIS sahifasida ulanadi)
EZO_TELEGRAM_BOT_TOKEN=
```
Muhim: Eskiz SMS matnlarini moderatsiya qiladi — ogohlantirish shablonini Eskiz kabinetida
oldindan tasdiqlating, aks holda Eskiz rad etadi va kartada shu xato ko‘rinadi.
Telefon raqamlar AI modelga yuborilmaydi; ular faqat SMS uchun saqlanadi.
`.env` o‘zgargach: `docker compose up -d --force-recreate api`.
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

## LEX.UZ: qonunlarni o‘rganish va ular bo‘yicha javob (2026-11-19)

Egasi ruxsati bilan (2026-11-19) LEX.UZ yoqildi. `.env` da shu qator bo‘lishi kerak:
```
EZO_OFFICIAL_SOURCES=lexuz
```
keyin `docker compose up -d --force-recreate api`.

- **Asosiy to‘plam:** chatga «Hokimiyat uchun asosiy qonunlarni o‘rgan» deb yozing. EZO 12 ta
  aktni (Konstitutsiya, Mahalliy davlat hokimiyati to‘g‘risida, Murojaatlar to‘g‘risida,
  Normativ-huquqiy hujjatlar, Ma’muriy tartib-taomillar, Davlat fuqarolik xizmati, Korrupsiyaga
  qarshi kurashish, Mehnat, Ma’muriy javobgarlik, Budjet, Yer va Soliq kodekslari) LEX.UZ’dan
  orqa fonda o‘qiydi — taxminan 3 daqiqa. Har bir raqam lex.uz’da tekshirilgan.
- **Boshqa har qanday akt:** savolda nomini aytsangiz kifoya — «Oila kodeksi bo‘yicha nikoh
  yoshi necha?». Bazada bo‘lmasa, EZO uni LEX.UZ’dan topib o‘qiydi (15–30 soniya), keyin javob
  beradi. Ikkinchi marta qayta qidirmaydi, faqat dolzarbligini tekshiradi.
- **Har javobda:** akt nomi, raqami, sanasi, moddasi, havolasi va holati (LEX.UZ ro‘yxatida
  «amaldagi» deb belgilangani). Holat aniq bo‘lmasa, EZO «tasdiqlanmagan» deydi va
  «amalda» deb da’vo qilmaydi.
- **Butun bazani** (yuz minglab hujjat) birdaniga tortib olmaydi — bu kunlab davom etadi va
  saytga yuk bo‘ladi. Kerakli aktlar ishlatilgan sari bilim bazasi o‘zi boyib boradi.

## Devonxona: murojaatlar, yig‘ilishlar, topshiriqlar, hisobotlar (2026-11-19)

Chap menyuda **«Devonxona»** (kiruvchi quti belgisi). Hammasini chatda ham aytish mumkin:

- «Yangi murojaat: Karimov Aziz, Navbahor MFY, ko‘cha chirog‘i yonmayapti, virtual qabulxona,
  Aliyevga topshirilsin» → **M-2026-0001** raqam bilan ro‘yxatga olinadi, muddati 15 kun
  (sahifada o‘zgartirish mumkin).
- «M-2026-0001 ga javob xati tayyorla: shu hafta tuzatiladi» → blankada Word **qoralama**.
  Imzolab yuborgach: «M-2026-0001 ga javob berildi».
- «Yig‘ilish bayonnomasini tuz: …(qaydlaringiz)…» → bayonnoma (Word, blankada) va undagi har
  bir topshiriq **T-2026-…** raqami bilan reestrga tushadi (mas’ul va muddati bilan).
- «T-2026-0003 bajarildi» → bajarilgan deb belgilanadi.
- «Muddati o‘tganlarni eslat» → mas’ullarga ogohlantirish **qoralamalari** (Tuman markazidagi
  kabi faqat siz «Yuborish» bosganda SMS/Telegram ketadi).
- «Haftalik hisobot tayyorla» / «Oylik hisobot» → murojaatlar, topshiriqlar va tuman
  loyihalari bo‘yicha Word hisobot (faqat bazadagi raqamlar).
- «Topshiriqlar holati» → muddati o‘tgan va yaqinlashganlar ro‘yxati.

Mas’ul eslatma olishi uchun u **Tuman markazi**dagi mas’ullar ro‘yxatida (telefon yoki Telegram
bilan) bo‘lishi kerak; aks holda sahifada sariq belgi chiqadi.

## Xodimlar Telegram orqali hisobot beradi (2026-11-19)

`.env` da `EZO_TELEGRAM_BOT_TOKEN` bo‘lsa, EZO o‘z botining xabarlarini har 20 soniyada o‘qiydi
(`EZO_TELEGRAM_POLL_SECONDS`, 0 — o‘chiq).

1. Mas’ulni bog‘lang: JARVIS sahifasida Telegram kontakt qo‘shing (u botga havola orqali
   /start bosadi), keyin **Tuman markazi → Mas’ullar bilan aloqa**da shu kontaktni tanlang.
2. Mas’ul botga yozadi:
   - «12» — bugun 12 ta qo‘shildi (bitta loyihasi bo‘lsa);
   - «xatlov 12» — aynan «Xatlov…» loyihasiga;
   - «jami 45» — umumiy son 45.
3. Bot darhol javob beradi: «✅ Qabul qilindi: «Xatlov 2026» — 17 / 100 xonadon (17%)».
   Tuman markazida raqam yangilanadi (manba: telegram), «Xatlov qalay ketyapti?» shu bilan javob beradi.

Notanish odamlarning xabarlariga bot javob bermaydi.

## Kompyuterni boshqarish — har amal sizning tasdig‘ingiz bilan (2026-11-19)

1. Kompyuteringizga **EZO desktop** ilovasini o‘rnating, **Sozlamalar → JARVIS → «Bu kompyuterni
   ulash»** (kodni EZO’ning JARVIS sahifasida tasdiqlaysiz), keyin
   **«Kompyuterni boshqarish»** belgisini yoqing (sukut bo‘yicha o‘chiq).
2. Chatda yoki JARVIS sahifasida yozing:
   - «Kalkulyatorni och», «Kompyuterda Wordni och» (Kalkulyator, Bloknot, Paint, Provodnik,
     Word, Excel, PowerPoint);
   - «Yuklamalar papkasida nima bor?» (Hujjatlar, Ish stoli ham);
   - «Ish stolidagi hisobot.docx faylini och», bo‘sh joyli nom qo‘shtirnoqda:
     «Yuklamalardagi «Oylik hisobot.xlsx» ni och»;
   - «https://lex.uz saytini och».
3. EZO vazifa yaratadi va **kutadi**: JARVIS sahifasida (yoki kompyuterdagi oynada) aniq nima
   bajarilishi yoziladi — «Ruxsat beraman» bosganingizdagina kompyuter bajaradi va imzolangan
   natijani qaytaradi.

Hech qachon: .exe, .bat, skriptlar va boshqa dasturlar ochilmaydi; papkadan tashqariga chiqilmaydi;
o‘chirish, o‘rnatish yoki buyruq qatori yo‘q. Rad etsangiz yoki «Kompyuterni boshqarish» o‘chiq
bo‘lsa, hech narsa bajarilmaydi.

## Ko‘nikmalar — EZO o‘zi uchun dastur yozadi, siz ruxsat berasiz (2026-11-19)

1. `.env` faylida `COMPOSE_PROFILES=documents,skills` qiling va `docker compose up -d --build`
   (yangi `skill-worker` xizmati ishga tushadi).
2. Chatda yozing: «O‘zingga kredit kalkulyatori vositasini qo‘sh». EZO kod yozadi va uni
   **qoralama** sifatida saqlaydi — hali ishlamaydi.
3. Chap menyudagi **«Ko‘nikmalar»** sahifasini oching → «Kodni ko‘rish». Kodni o‘qing,
   avtomatik tekshiruv natijasini ko‘ring va **«Ruxsat beraman»** ni bosing. Ruxsat aynan shu
   kodga (SHA-256 izi) beriladi: EZO keyin kodni o‘zgartirsa, ruxsat avtomatik bekor bo‘ladi.
4. Chatda ishlating: «Kredit kalkulyatori: 50 mln, 24 oy, 22%». EZO ko‘nikmani yopiq qafasda
   ishga tushiradi va **haqiqiy natija** bilan javob beradi (oylik to‘lov 2 593 908 so‘m).

Qafas: har ishga tushirish uchun yangi konteyner — internet yo‘q, disk faqat o‘qish uchun,
256 MB xotira, 32 jarayon, 20 soniya, hech qanday imtiyoz yo‘q. Kodda faqat hisob-kitob va matn
modullari bo‘lishi mumkin (math, datetime, json, re, …); `os`, `socket`, `open`, `eval` va
shunga o‘xshashlar tekshiruvdan o‘tmaydi va ularga ruxsat berib bo‘lmaydi. Ruxsatni faqat EZO
egasi beradi; «O‘chirish» bilan istalgan vaqtda to‘xtatasiz.
