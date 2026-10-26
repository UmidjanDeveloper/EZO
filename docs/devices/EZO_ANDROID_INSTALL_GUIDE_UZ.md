# EZO — Android telefonga o‘rnatish yo‘riqnomasi

## 0. Hozirgi holat (halol)

| Narsa | Holat |
|---|---|
| `EZO-debug.apk` (paket `uz.ezo.mobile`, Android 7.0+ / minSdk 24) | GitHub Actions’da quriladi; **debug imzo** bilan (Play Store emas) |
| Emulyatorda sinov | O‘TDI: CI’da Android 14 emulyatoriga o‘rnatildi, haqiqiy EZO serveriga ulandi, desktopda boshlangan suhbatni ochdi va telefondan yuborilgan xabar o‘sha suhbatda saqlandi ([40080361627](https://github.com/UmidjanDeveloper/EZO/actions/runs/40080361627)). Haqiqiy telefonda hali sinalmagan. |
| Haqiqiy telefonda | **Hali sinalmagan** — mikrofon, kamera va sizning tarmog‘ingiz faqat telefonda tekshiriladi |
| iPhone (iOS) | **Mavjud emas** — macOS/Xcode va Apple Developer hisobi kerak |

## 1. Server tayyorlash (telefon uchun)

Telefon serverga tarmoq orqali ulanadi, shuning uchun:

1. Serverning `.env` faylida:
   ```
   EZO_AUTH_MODE=token
   EZO_API_TOKEN=<uzun tasodifiy token>
   EZO_CORS_ORIGINS=http://localhost:3000,https://localhost
   ```
   (`https://localhost` — EZO ilovasining ichki manzili; uni qo‘shmasangiz ilova ulana olmaydi.)
2. Serverni qayta ishga tushiring: `docker compose up -d`.
3. Kompyuteringizning lokal IP manzilini bilib oling (PowerShell: `ipconfig` →
   masalan `192.168.1.20`). Telefon va kompyuter **bir xil Wi‑Fi** da bo‘lsin.
4. Uydan tashqarida ishlatish uchun HTTPS + VPN kerak (alohida, egasi tasdiqlaydigan ish).

## 2. APK’ni yuklab olish va tekshirish

1. GitHub → **Actions → Devices** → oxirgi yashil ishga tushirish → `ezo-android`.
2. Zip ichida `EZO-debug.apk` va `apk-badging.txt` (paket nomi, SDK, ruxsatlar va **SHA256**).
3. Kompyuterda tekshirish: `Get-FileHash .\EZO-debug.apk -Algorithm SHA256` → `apk-badging.txt` dagi qiymat bilan bir xil bo‘lishi kerak.

## 3. O‘rnatish

1. APK’ni telefonga o‘tkazing (USB, Telegram’da “Saqlangan xabarlar” va h.k.).
2. Faylni oching → Android **“Noma’lum manbalardan o‘rnatish”**ga ruxsat so‘raydi →
   faqat shu ilova (masalan, Fayllar) uchun ruxsat bering → **O‘rnatish**.
3. Play Protect ogohlantirsa: bu imzosiz/debug test build; faqat o‘zingiz tekshirgan APK uchun davom eting.

## 4. Birinchi ishga tushirish

1. EZO’ni oching → **Sozlamalar** bo‘limi ochiladi.
2. **EZO server manzili:** `http://192.168.1.20:8000` (o‘z IP’ingiz).
   Debug build LAN’dagi `http://` manzilga ulana oladi; release build faqat `https://` ishlatadi.
3. **Kirish tokeni:** serverdagi `EZO_API_TOKEN`. Telefonning shifrlangan xotirasida saqlanadi.
4. **Saqlash va ulanish** → “Suhbat” bo‘limi ochilsa, ulandingiz.

## 5. Foydalanish

- **Suhbat:** desktop yoki vebda boshlangan suhbatlar ro‘yxatda ko‘rinadi — xuddi
  shu suhbatni davom ettirasiz.
- **🎤** — gapirish (birinchi marta mikrofon ruxsati so‘raladi). Serverda ovoz kaliti kerak.
- **📷** — rasmga oling va savol bering (serverda rasmni tushunadigan AI kerak).
- **📄** — hujjat:
  - TXT/MD/CSV — telefon o‘zi o‘qiydi, mazmunini so‘raydi;
  - PDF/DOCX/EPUB/rasm — EZO Student’ga yuboriladi va serverdagi izolyatsiyalangan
    hujjat ishchisi o‘qiydi. Ishchi ishlamayotgan bo‘lsa, ilova buni ochiq aytadi va hujjat navbatda qoladi.
- **Loyihalar / Xotira / Eslatmalar** — eslatmalar uchun bildirishnoma ruxsati so‘raladi.

## 6. Muammolar

| Belgi | Yechim |
|---|---|
| Ulanmaydi | Bir xil Wi‑Fi’mi? IP to‘g‘rimi? Kompyuter firewall’i 8000-portni bloklamayaptimi? `EZO_CORS_ORIGINS` da `https://localhost` bormi? |
| “Kirish tokeni noto‘g‘ri” | Serverdagi `EZO_API_TOKEN` bilan bir xil yozing |
| Ovoz ishlamaydi | Mikrofon ruxsati (Sozlamalar → Ilovalar → EZO → Ruxsatlar) va serverdagi ovoz kaliti |
| Hujjat “navbatda” qoladi | Serverda hujjat ishchisi ishga tushirilmagan (egasi tasdiqlaydigan alohida host) |

## 7. Maxfiylik, o‘chirish va eksport

- Ovoz va rasm faqat siz bosganingizda yuboriladi; serverda saqlanmaydi.
- **O‘chirish:** telefon Sozlamalar → Ilovalar → EZO → O‘chirish (token ham o‘chadi).
- **Ma’lumot eksporti:** veb ilovada Xotira → eksport. Server ma’lumotlari sizning serveringizda qoladi.
