# EZO — Windows kompyuterga o‘rnatish yo‘riqnomasi

Bu yo‘riqnoma **haqiqatda mavjud** build va sozlamalarga asoslangan. Nimalar ishlashi
tekshirilgan, nimalar hali sizning kompyuteringizda sinalmagani alohida ko‘rsatilgan.

## 0. Muhim: hozirgi holat

| Narsa | Holat |
|---|---|
| O‘rnatuvchi (`EZO-Setup-0.1.0.exe`, NSIS, Windows x64) | GitHub Actions’da har safar quriladi va GitHub’ning Windows serverida jim (`/S`) o‘rnatib, ishga tushirib tekshiriladi |
| Kod imzosi (code signing) | **Yo‘q** — Windows SmartScreen ogohlantiradi (pastga qarang) |
| Kalkulyator ochish, ruxsat berilgan papkadan fayl topish, faol oynaga yozish, ekran rasmi | GitHub Windows serverida ishladi; **sizning kompyuteringizda hali sinalmagan** |
| Ovozli suhbat (o‘zbekcha) | Kod tayyor; mikrofon, karnay va serverda AI/ovoz kaliti kerak — hali jonli sinalmagan |
| JARVIS (Downloads → PDF → Telegram) | Kod tayyor va testlardan o‘tgan; sizning kompyuteringiz, Telegram bot va hujjat ishchisi bilan hali jonli sinalmagan |

## 1. Kerakli narsalar

- Windows 10 yoki 11 (64-bit).
- **EZO serveri.** Eng oddiy yo‘l — shu kompyuterning o‘zida Docker bilan:
  1. [Docker Desktop](https://www.docker.com/products/docker-desktop/) o‘rnating.
  2. EZO repozitoriyasini yuklab oling, `.env.example` dan nusxa olib `.env` deb nomlang.
  3. `.env` ga kamida bitta AI kaliti yozing (masalan `OPENAI_API_KEY=` yoki
     `GEMINI_API_KEY=`). Ovoz uchun `OPENAI_API_KEY` yoki `ELEVENLABS_API_KEY` kerak.
  4. PowerShell’da: `docker compose up --build` — server `http://localhost:8000` da ishlaydi.
- Kalitlarni hech qachon desktop ilovasiga yozmang: ular faqat serverning `.env` faylida turadi.

## 2. O‘rnatuvchini yuklab olish

1. GitHub’da: **Actions → Devices** ish jarayoni → integratsiya bo‘g‘inidagi oxirgi
   **yashil (✓)** ishga tushirish.
2. Pastdagi **Artifacts** bo‘limidan `ezo-windows` ni yuklab oling va zip’ni oching.
3. Faylning haqiqiyligini tekshiring (PowerShell):
   ```powershell
   Get-FileHash .\EZO-Setup-0.1.0.exe -Algorithm SHA256
   ```
   Natijani o‘sha ishga tushirishdagi `install.txt` / release hujjatidagi SHA256 bilan solishtiring.

## 3. O‘rnatish

1. `EZO-Setup-0.1.0.exe` ni ishga tushiring.
2. Imzo yo‘qligi sababli **“Windows protected your PC”** chiqadi. Bu fayl sizning
   GitHub Actions’ingizda qurilganini tekshirgan bo‘lsangiz: **More info → Run anyway**.
   (Begona joydan olingan `.exe` uchun buni qilmang.)
3. O‘rnatish joyini tanlang (standart: `%LOCALAPPDATA%\Programs\EZO`), “Finish”.

## 4. Birinchi ishga tushirish

- Ekran tepasida kichik **EZO pill** chiqadi; soat yonida (tray) EZO belgisi bor.
  Birinchi ishga tushirishda **Sozlamalar** oynasi o‘zi ochiladi.
- Pill’dagi nuqta serverning haqiqiy holati: yashil — AI tayyor, sariq — server bor, AI kaliti
  yo‘q (javoblar oflayn), qizil — serverga ulanib bo‘lmayapti (yuz kulrang bo‘ladi).
- **Ctrl+Alt+H** — pill’ni ko‘rsatish/yashirish (tray belgisiga bosish ham shuni qiladi).
- Sozlamalardagi **Ilova tili** (o‘zbek/ingliz/rus) pill, sozlamalar, dialoglar va xato
  xabarlariga taalluqli; EZO gapirgan tilda javob beradi.
- Tray → **Sozlamalar**:
  - **Server manzili:** `http://localhost:8000` (shu kompyuterdagi server) yoki
    `https://...` (masofaviy server).
  - **Kirish tokeni:** serverda `EZO_AUTH_MODE=token` bo‘lsa, `EZO_API_TOKEN` ni kiriting.
    Token Windows DPAPI bilan shifrlanib saqlanadi va qayta ko‘rsatilmaydi.
  - **“Ulanishni tekshirish”** — “Ulandi: …” chiqishi kerak.
- **Barcha ruxsatlar boshida o‘chiq.** Faqat kerakligini yoqing: Kalkulyator/Bloknot/
  Paint/Explorer ochish, ovoz balandligi, faol oynaga yozish, ekranni tahlil qilish
  (har safar alohida so‘raladi), fayl qidirish uchun papkalar.

## 5. Foydalanish

- **Ctrl+Alt+Space** (o‘zgartirish mumkin) — gapirishni boshlash/to‘xtatish.
  Birinchi marta Windows mikrofon ruxsatini so‘raydi.
- Misollar: “Kalkulyatorni och”, “hisobot faylini top”, “Yoz: Salom!”,
  “Ekranda nima borligini tushuntir”. Boshqa savollar oddiy suhbat bo‘ladi va
  suhbat serverda saqlanadi — telefon va veb ilovada ham ko‘rinadi.
- Pill holatlari: **Tinglayapman** (qizil halqa) → **Taniyapman** (yozuv matnga aylanmoqda) →
  **O‘ylayapman** yoki **Bajaryapman** (kompyuterda amal) → **Gapiryapman** → **Bajarildi**.
  **■** tugmasi haqiqatan to‘xtatadi: serverga ketgan so‘rov bekor qilinadi, kech kelgan javob ko‘rsatilmaydi.
- **☰** — suhbat tarixi serverdan: oxirgi xabarlar, boshqa suhbatga o‘tish, yangi suhbat.
- JARVIS vazifasi ketayotganda pill’da joriy qadam yoki “tasdiq kutilmoqda” yoziladi; **Vazifani bekor qilish** serverda bekor qiladi.

## 6. JARVIS (Downloads → PDF → foizlar → Telegram)

1. Serverning `.env` ga `EZO_TELEGRAM_BOT_TOKEN=` (@BotFather’dan) yozing va serverni qayta ishga tushiring.
2. Desktop: Sozlamalar → **JARVIS vazifalari** → **Papkani tanlash…** (Downloads) →
   **Bu kompyuterni ulash**. Ekranda 6 xonali kod chiqadi.
3. Veb ilova → **JARVIS** sahifasi → “Ulangan qurilmalar”da shu kodni kiriting → “ulangan”.
4. Shu sahifada “Telegram qabul qiluvchilar”ga masalan **Baxtiyor** ni qo‘shing,
   chiqqan havolani unga yuboring; u botda **Start** bosgach, **Tekshirish**ni bosing.
5. Endi gapiring: *“Downloads ichidagi eng oxirgi faylni och, PDF'ga aylantir, foiz
   ko'rsatkichlarini undan oldingi faylga o'xshatib tayyorla va Telegram'da Baxtiyorga yubor.”*
   - Desktop qaysi fayllar serverga ketishini ko‘rsatib, **ruxsat so‘raydi**.
   - Telegram’ga yuborishdan oldin qabul qiluvchi va fayllar ko‘rsatilib, **yana tasdiq so‘raladi**.
   - “Yuborildi” faqat Telegram haqiqiy xabar ID qaytarganda yoziladi.
6. PDF/DOCX/XLSX fayllarni o‘qish uchun serverda alohida **hujjat ishchisi**
   (`python -m ezo_api.jarvis.worker`) ishlashi kerak. U bo‘lmasa, vazifa shu bosqichda
   kutib turadi (TXT/CSV fayllar ishchisiz ishlaydi).

## 7. Muammolar

| Belgi | Sabab va yechim |
|---|---|
| “EZO serveriga ulanib bo‘lmadi” | Server ishlayaptimi (`docker compose ps`)? Manzil to‘g‘rimi? |
| “Kirish tokeni noto‘g‘ri” | Serverdagi `EZO_API_TOKEN` bilan bir xilmi? |
| “Serverda nutqni aniqlash … sozlanmagan” | `.env` ga ovoz kaliti qo‘shing |
| Ctrl+Alt+Space ishlamaydi | Boshqa dastur band qilgan — Sozlamalarda boshqa tugma tanlang |
| “Bu amal uchun ruxsat berilmagan” | Sozlamalarda shu ruxsatni yoqing |
| JARVIS: “No paired EZO desktop companion” | 6-bo‘limdagi ulash bosqichlarini bajaring |

## 8. Maxfiylik

- Ruxsatlar har doim sizning qo‘lingizda; istalgan payt o‘chirasiz.
- Ovoz yozuvi faqat tugmani bosganingizda olinadi va serverda saqlanmaydi.
- Ekran rasmi faqat siz tasdiqlaganingizda, faqat shu so‘rov uchun yuboriladi.
- JARVIS faqat siz tanlagan **bitta** papkadagi eng yangi hujjatlarni, har safar
  ruxsat so‘rab, o‘qiydi; ichki papkalar va boshqa joylar o‘qilmaydi.

## 9. O‘chirish va ma’lumotlar

- **Dasturni o‘chirish:** Windows Sozlamalar → Ilovalar → **EZO** → O‘chirish.
- **Kompyuterdagi ma’lumotlar:** `%APPDATA%\EZO` (`settings.json`, shifrlangan
  `token.bin` va `jarvis-key.bin`). To‘liq tozalash uchun shu papkani o‘chiring.
- **Serverdagi ma’lumotlar:** veb ilovada Xotira → eksport; JARVIS sahifasida
  qurilmani “Bekor qilish”. Hammasini o‘chirish: `docker compose down -v` (qaytarib bo‘lmaydi).
