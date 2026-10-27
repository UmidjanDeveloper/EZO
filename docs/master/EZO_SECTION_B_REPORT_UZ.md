# EZO OS — B bo‘lim: humanoid mahsulot hisoboti (egasi uchun, o‘zbekcha)

Sana: 2026-10-27. Tarmoq: `section-b/humanoid-product`, qoralama PR
[#56](https://github.com/UmidjanDeveloper/EZO/pull/56), integratsiya bazasi `abb9016`.
Hech narsa birlashtirilmadi, joylanmadi, hech qanday pullik xizmat yoqilmadi.

Holatlar: **BAJARILDI / QISMAN / BLOKLANGAN / KUTILMOQDA**. Foizlar yo‘q. «Ishlaydi» degani —
haqiqiy ishga tushirishda (haqiqiy brauzer, CI’dagi haqiqiy Windows, haqiqiy emulyator, haqiqiy
API) tekshirilgan degani. Jismoniy kompyuter, telefon, kamera yoki mikrofon bu yerda yo‘q —
ular bilan bog‘liq hamma narsa **KUTILMOQDA** deb belgilangan.

## 1. Qisqacha

| Savol | Javob |
|---|---|
| Humanoid odamga o‘xshadimi? | Avvalgi kontur-figuraga **yuz qatlami** qo‘shildi: ko‘zlar (oq, rangdor parda, qorachiq), ko‘z nigohi (ko‘zlar boshdan oldin buriladi), ko‘z qovoqlari (2–6 soniyada bir pirpiratadi, oflaynda yarim yumuq), qoshlar (tinglaganda ko‘tariladi, o‘ylaganda tushadi), lablar va jag‘ (faqat EZO’ning o‘z ovozi o‘lchovi bilan ochiladi), tabassum (muvaffaqiyat) / tushgan burchaklar (xato); yumshoq yon yorug‘lik. Bu — EZO’ning o‘z zarracha-uslubi; fotorealizm da’vo qilinmaydi. |
| Windows | Doiracha (pill) **katta sahnaga** (420×640) kengayadi: to‘liq humanoid + ovoz halqasi; tray menyusida «Katta/Kichik ko‘rinish»; birinchi ishga tushirishda 3 qadamli xush kelibsiz; sozlamalarda mikrofon (o‘chirish mumkin), kamera (sukut bo‘yicha o‘chiq), tejamkor rejim; MIC/CAM ko‘rsatkichlari faqat haqiqatan ochiq bo‘lganda; yashirilganda/chiqishda hammasi yopiladi. |
| Android | Ovoz sahnasida kamera qatori (holat, tugma, maxfiylik matni), barmoq — «kamera emas» deb belgilangan zaxira; sahna yopilganda yoki ilova fonga o‘tganda kamera va figura to‘xtaydi; tejamkor rejim sozlamasi; emulyator testi endi sahnani haqiqiy qurilmada ochadi. |
| Veb | O‘sha sahna, o‘sha qoidalar: kamera qatori, belgilangan sichqoncha zaxirasi, yashirin tab — kamera to‘xtaydi; 10 marta ochib-yopishda xotira oshmaydi. |
| Kamera/imo-ishora | **KUTILMOQDA (Codex)**. Shartnoma (`TrackingFrame, HeadPose, HandTarget, MotionIntent, ClapEvent, VisionStatus, VoiceIntent`) va `AttentionDriver` tayyor, uchala ilovada ulanish joyi bor. Bu build’da dvigatel yo‘q — shuning uchun kamera tugmasi o‘chiq va sababini aytadi. Testlar faqat **simulyatsiya** kadrlari bilan; ekranda ham «SIMULYATSIYA» yozuvi chiqadi. |
| Ovoz | Pipeline avvalgidek haqiqiy API bilan ishlaydi; jag‘ animatsiyasi EZO’ning o‘z nutqi o‘lchovidan (`captureStream`) boshqariladi, o‘lchov bo‘lmasa — ritm, lekin xira va «o‘lchov» deb ko‘rsatilmaydi. Haqiqiy o‘zbekcha ovoz — serverda kalit (OpenAI/ElevenLabs) bo‘lsa. |

## 2. `packages/avatar` da nima yaxshilandi (BAJARILDI)

- `face.ts` (yangi): pirpiratish egri chizig‘i, ko‘z nishoni, qosh/og‘iz/tabassum/qovoq miqdorlari — toza funksiyalar, GPU’siz testlangan.
- `figure.ts`: `eye`, `lid`, `brow`, `mouth` nuqta turlari yuz yuzasi oldida (`faceZ`); `EYE`, `MOUTH` o‘lchamlari eksport qilinadi.
- `shaders.ts`: rangdor parda nigoh bilan siljiydi, qovoq yopiladi, qosh ko‘tariladi, pastki lab va jag‘ ovoz bilan ochiladi, burchaklar tabassumda ko‘tariladi; bosh/bo‘yin uchun yon yorug‘lik.
- `avatar.ts`: pirpiratish taymeri, ko‘zlar boshdan tezroq buriladi, `power: "low"` (30 kadr/s; kam xotira/data-saver qurilmalarda avtomatik), `setLowPower`, `setActive` (yashirin oynada chizish to‘xtaydi), `getFace()`; 2D zaxira chizmasida ham yuz bor.
- `sensing.ts` (yangi): Codex dvigateli bilan shartnoma va `AttentionDriver` (qo‘l → bosh → sichqoncha/barmoq → tinch; eski/ishonchsiz/NaN kadrlar nigohni qo‘yib yuboradi; yashirin ko‘rinish hech qachon kuzatmaydi; `stop()`).
- Testlar: 28/28 (`face`, `sensing`, `figure`, `states`, kamera).

Rasmlar (kodning o‘zidan, Chromium SwiftShader): `docs/devices/img/humanoid-states-bust.jpg`,
`humanoid-states-head.jpg`, `humanoid-face-speaking.jpg`, `windows-stage.jpg`, `android-stage.jpg`,
`android-welcome.jpg`. Bular reklama rasmi emas, jismoniy qurilma surati ham emas.

## 3. Windows, Android, veb — nima o‘zgardi

**Windows (`apps/desktop`)** — BAJARILDI (CI’dagi Windows VM’da o‘rnatish + o‘z-o‘zini tekshirish + o‘chirish)
- Sahna: `⤢` tugmasi / tray → oyna 420×640 ga kengayadi, byust humanoid + ovoz halqasi; bir vaqtda bitta figura (10 marta kengaytirib-yig‘ishda ikkinchi halqa paydo bo‘lmaydi, xotira oshmaydi — spec).
- Sozlamalar: «Mikrofon va kamera» bo‘limi (mikrofon yoqiq, o‘chirish mumkin; kamera o‘chiq, yoqish mumkin — lekin dvigatelsiz ochilmaydi, shunday deb yozilgan), «Tejamkor rejim», birinchi ishga tushirish xush kelibsiz (uz/en/ru).
- Asosiy jarayon faqat pill oynasiga va faqat ruxsat berilgan media turiga ruxsat beradi (`allowOnlyAllowedMedia`). Electron xavfsizligi o‘zgarmadi: contextIsolation, sandbox, CSP, tor preload.
- Yashirish (Ctrl+Alt+H, tray), chiqish, sozlamada o‘chirish → mikrofon, kamera va chizish darhol to‘xtaydi.
- Kamera: `src/renderer/sensing.ts` ulanish joyi; dvigatel yo‘q → tugma o‘chiq + sabab; sichqoncha zaxirasi «(kamera emas)» deb yozilgan.
- Topilgan va tuzatilgan nuqson: sahna kamerasini ishga tushirishda holat qayta chaqiruvi sessiya o‘zgaruvchisiga erta murojaat qilardi (TDZ) — spec topdi, tuzatildi.

**Android (`apps/mobile`)** — BAJARILDI (emulyator), jismoniy telefon KUTILMOQDA
- Kamera qatori, `AttentionDriver` + barmoq zaxirasi, fon/sahna yopilishi → kamera va figura to‘xtaydi, tejamkor rejim sozlamasi, uch tilda matnlar.
- `tests/e2e/devices/android-smoke.mjs`: endi ovoz sahnasini haqiqiy emulyatorda ochadi, WebGL renderer, nuqtalar soni, quvvat rejimi va kamera tugmasi o‘chiqligini tekshiradi, skrinshot oladi, yopadi.
- `tests/e2e/specs/mobile-stage.spec.ts`: qurilgan ilova xotiradan xizmat qilinadi: oflayn sahna, o‘chiq kamera tugmasi, 10 marta ochib-yopish, simulyatsiya belgilanishi.

**Veb (`apps/web`)** — BAJARILDI
- `CameraAttention` qatori ovoz sahnasida; `EzoHumanoid` figurani ulashadi va sichqoncha nigohini drayverga yo‘naltiradi; yashirin tab yoki sahnadan chiqish — kamera to‘xtaydi.
- `tests/e2e/specs/camera-attention.spec.ts`: dvigatelsiz holat, simulyatsiya belgisi, qo‘l nishoni, yashirin tab, 10 marta ochib-yopish.

## 4. Haqiqiy backend/ovozga nima ulangan

- Suhbat, tarix, JARVIS vazifalari, server holati — avvalgidek haqiqiy `apps/api` bilan (o‘zgarmadi).
- Ovoz: yozish → `/api/voice/transcribe` → javob → `/api/voice/speak`; jag‘/yuz animatsiyasi EZO ovozining haqiqiy o‘lchovi bilan; o‘lchov yo‘q bo‘lsa — ritm, xira, «o‘lchov» deb aytilmaydi. Provayder xatosi aynan ko‘rsatiladi.
- Kamera: hech narsa backendga yuborilmaydi; yozib olinmaydi; yuz tanilmaydi; dvigatel yo‘q.

## 5. Codex’ning sensing dvigatelini nima kutyapti (KUTILMOQDA)

- Provider ulanishi: `window.ezoSensingProvider` o‘rniga haqiqiy `start({video,onStatus,onHead,onHand,onClap})` ni uchala ilovadagi `sensing.ts` ga qo‘shish (bir faylli o‘zgarish). Dvigatel `VisionStatus` ni haqiqiy OS/brauzer ruxsatidan olib berishi shart (`denied`, `unavailable` ni taxmin qilmaslik).
- Qo‘l nishoni (`HandTarget.raised`), qarsak (`ClapEvent`) — UI tayyor: «EZO qo‘lingizga qaraydi», «Qarsak eshitildi».
- Jismoniy kamera bilan tekshirish: bu yerda kamera yo‘q; simulyatsiya testlari jismoniy xatti-harakatni isbotlamaydi.
- Model litsenziyasi/SHA tasdig‘i (face-tracking README’da yozilganidek) — egasining qarori.

## 6. Test natijalari (haqiqiy raqamlar)

| To‘plam | Natija |
|---|---|
| `packages/avatar` vitest | 28/28 |
| `apps/desktop` vitest + typecheck + build | 69/69 (2 o‘tkazib yuborilgan: Windows’ga xos) |
| `apps/mobile` vitest + typecheck + build + `cap sync` | 19/19 |
| `apps/web` vitest + lint + typecheck | 97/97 |
| Playwright `desktop-pill` | 9/9 (4 yangi) |
| Playwright `camera-attention` (veb) | 3/3 (yangi) |
| Playwright `mobile-stage` | 2/2 (yangi) |
| Playwright `accessibility` | 11/11 |
| Playwright to‘liq to‘plam (lokal) | __E2E_TOTAL__ |
| CI / Devices / Security (`0b3ed4a` yoki yakuniy head) | __CI__ |

## 7. Jismoniy kompyuter/telefon kerak bo‘lgan narsalar (KUTILMOQDA)

1. Windows: `ezo-windows` artefaktidan o‘rnatish; SmartScreen; xush kelibsiz → server/token; `⤢` sahna; mikrofon bilan o‘zbekcha gapirish (server kaliti bilan); kamera sozlamasi — dvigatel kelguncha o‘chiq qoladi.
2. Android: `EZO-debug.apk`; xush kelibsiz; sahna, 🎤; kamera tugmasi o‘chiq va sababi ko‘rinadi; batareya rejimi (sozlamada yoqib ko‘ring).
3. Kamera/qo‘l/qarsak: Codex dvigateli ulangandan keyin, haqiqiy kamera bilan.
4. iOS: faqat tayyorgarlik (Capacitor, bir xil `sensing.ts` shartnomasi); macOS/Xcode/imzo yo‘q — IPA da’vo qilinmaydi.

## 8. Qolgan to‘siqlar

- Sensing dvigateli (Codex) — kamera/imo-ishora funksiyalarining hammasi.
- Ovoz provayderi kalitlari (OpenAI/ElevenLabs) — tabiiy o‘zbekcha ovoz.
- Kod imzosi (Windows), keystore (Android), Apple hisobi (iOS).
- Jismoniy qurilmalar — hech biri bu yerda yo‘q.

Bu hisobot «tirik humanoid tayyor» demaydi: ko‘z/qo‘l/kamera va jismoniy ovoz testlari o‘tmagan.
«100% xatosiz» yoki «fotorealistik» kabi da’volar yo‘q.
