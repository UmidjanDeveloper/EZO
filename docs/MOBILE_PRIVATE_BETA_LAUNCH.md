> **Superseded for the current zero-budget mission:** use [Zero-budget private beta](ZERO_BUDGET_PRIVATE_BETA.md).
> This historical paid runbook is not launch authorization. Its native API/OCR and job claims are stale; do not follow them.

# EZO private beta: telefon orqali ishga tushirish

**Hozir deploy qilinmaydi.** Bu qo‘llanma kelajakdagi alohida tasdiqlangan launch uchun.
Joriy P0/P1 vazifasi: [P0 hisobot](P0_HARDENING_REPORT.md),
[GitHub himoyasi](GITHUB_P0_PROTECTION.md) va [Student reja](P1_EZO_STUDENT_V1_PLAN.md).

Android yoki iPhone brauzeri yetarli. Kompyuter, terminal ilovasi va dastur kodini
qo‘lda yozish shart emas. Tayyor SQL faylni Supabase muharririga ko‘chirish mumkin;
maxfiy qiymatlar faqat xizmatlarning himoyalangan sozlamalariga kiritiladi.
Chatga parol, token, provider kaliti yoki to‘liq DATABASE_URL yubormang.

**Avval:** [tekshiruv hisobotini](PRIVATE_BETA_VALIDATION.md) va
[xavflar reyestrini](PRIVATE_BETA_SECURITY_RISK_REGISTER.md) o‘qing. Ochiq CRITICAL
xavf bo‘yicha mustaqil review va aniq qarorsiz deployment’ni tasdiqlamang.
To‘lov, repository sozlamalari, merge va Deploy — egasining alohida qarorlari.
Codex ularni avtomatik bajarmaydi. Quyidagi misollar haqiqiy credential emas.

## 1. GitHub loyihasini ochish

- Manzil: https://github.com/UmidjanDeveloper/EZO → **Code → branch tanlash**.
  Branch: **claude/gifted-goodall-bpf01s**, main emas. Fayllar va oxirgi commit ko‘rinsin.
- Sozlamalar ko‘rinmasa: Chrome’da **⋮ → Desktop site**; Safari’da sahifa menyusidan
  **Request Desktop Website**. GitHub mobil ilovasi ayrim admin sozlamalarini ko‘rsatmaydi.

## 2. Codex PRini tekshirish

- Manzil: https://github.com/UmidjanDeveloper/EZO/pulls → tegishli PR → **Files changed**.
  Head: **fix/final-private-beta-hardening**; base: **claude/gifted-goodall-bpf01s**.
- PR tavsifi, testlar va xavflarni o‘qing; Claude’dan mustaqil review oling.
- PR topilmasa: push qilingan branch hali PR emas. Codex muhitining tarmoq
  sozlamalarida api.github.com uchun saqlangan ruxsatni qo‘llang; zarur bo‘lsa
  muhitni publish qiling va Codex’dan davom ettirishni so‘rang. Yangi tokenni chatga yubormang.
- Muqobil telefon yo‘li: [branchlarni solishtirish](https://github.com/UmidjanDeveloper/EZO/compare/claude/gifted-goodall-bpf01s...fix/final-private-beta-hardening)
  → **Create pull request**. Base/head yuqoridagidek bo‘lsin; bu hali merge emas.

## 3. CI natijalari

- Manzil: https://github.com/UmidjanDeveloper/EZO/actions yoki **PR → Checks**.
  Run aynan PRning oxirgi commitiga tegishli bo‘lsin; eski yashil run yetarli emas.
- Qizil jobni oching, xato nomi va run havolasini saqlang. Maxfiy loglarni ulashmang;
  tuzatishsiz merge qilmang.
- **Security run → Artifacts** orqali to‘liq JSON hisobotlar olinadi.
  Fixable-CVE gate yashil bo‘lishi unfixed HIGH/CRITICAL yo‘q degani emas.
- Oxirgi commitning Python, Node va Container Security joblarini ham tekshiring.
  Yangilangan container job nomi birinchi PR run’da paydo bo‘lgach rulesetga aynan
  GitHub ko‘rsatgan nom bilan qo‘shing; eski Security #12 nomini taxminan ko‘chirmang.

## 4. Branch protection / ruleset

- Manzil: https://github.com/UmidjanDeveloper/EZO/settings/rules
- Tekshiruvda Status nomli enabled ruleset bor, ammo branch include sharti bo‘sh,
  PR va required CI talablari yo‘q; default branch himoyalanmagan. Uni tahrirlang
  yoki quyidagi to‘liq rulesetni yarating. Faqat Enabled yozuvi yetarli emas.
- Desktop-site rejimida **Settings → Rules → Rulesets → New ruleset → New branch ruleset**.
  Nom: EZO integration protection. **Enforcement status: Active**.
- **Target branches → Include by pattern:** claude/gifted-goodall-bpf01s.
- Yoqing: **Restrict deletions**, **Block force pushes**, **Require a pull request
  before merging**, **Require status checks to pass**, **Require branches to be up to date**.
- Quyidagi aniq nomlar CI #84 GitHub sahifasidan tekshirilgan. Required checks’ga tanlang:
  - Secret scan (gitleaks, full history)
  - API (lint, types, tests on SQLite + PostgreSQL)
  - Web (lint, types, unit tests, build, e2e)
  - Docker (API + web images, Compose config, API smoke test)
- **Bypass list** bo‘sh qolsin. Force push, branch o‘chirish va auto-merge istisnolarini
  yoqmang. Deployment/merge-queue talablarini ular tayyor bo‘lmaguncha qo‘shmang.
- Bir kishilik loyiha uchun required approvals **0** bo‘lishi mumkin: PR va CI baribir
  shart; Claude review’ini o‘zingiz tekshirasiz. **1 approval** faqat boshqa ishonchli
  GitHub reviewer bo‘lsa yoqilsin. Claude chatidagi xulosa GitHub approval emas.
- Public repo standart rulesetlari GitHub Free’da mavjud; private repo himoyasi tarifga
  bog‘liq. Tarif/visibility’ni roziliksiz o‘zgartirmang.
- https://github.com/UmidjanDeveloper/EZO/rules da Active holatini va PRda pending yoki
  qizil required check merge’ni to‘sishini tekshiring. Sozlama yo‘q bo‘lsa owner/admin
  hisobi va tarifni tekshiring; himoyani bypass qilib sinamang.

## 5. Tasdiqlangan PRni merge qilish

- **PR → Conversation → Checks / Review → Merge pull request**.
- Faqat oxirgi commit testlari, xavf qarori va Claude review’i tasdiqlangach merge qiling.
  To‘liq merge commit SHAni release qaydiga saqlang.
- Ulangan hosting auto-deploy qilishi mumkinligini avval tekshiring. Render blueprint’da
  auto-deploy o‘chiq. Code review roziligi to‘lov yoki tasdiqlanmagan deployga rozilik emas.

## 6. Supabase va vector

- Manzil: https://supabase.com/dashboard → **Organization → New project**.
  Nom: ezo-private-beta; mintaqa Render’ga yaqin, masalan Frankfurt.
  Tarifni tekshirib, faqat to‘lovga roziligingizdan keyin yarating.
- Faqat EZO uchun yangi dedicated baza ishlating. Parol menejerida kamida 40 ta
  harf/raqamli tasodifiy parol yarating; uni chat yoki ommaviy encoder’ga kiritmang.
- **Database → Extensions → vector → Enable**.
  **Project Settings → Data API** (ayrim UIlarda API) orqali Data API’ni o‘chiring.
- Kutilgan natija: vector yoqilgan, anon/authenticated rollar EZO ma’lumotini o‘qiy olmaydi.
  Aks holda production preflight rad etishi kerak; bu himoyani o‘chirmang.

## 7. Baza roli va TLS

- Yangi dedicated loyiha uchun [tayyor SQL](../deploy/supabase-private-beta-role.sql)ni
  **SQL Editor → New query → Run** orqali qo‘llang. Kod yozish shart emas.
  Mavjud/shared bazaga ko‘r-ko‘rona qo‘llamang; avval backup va obyekt egalarini tekshiring.
- **Database → Roles → ezo_app** orqali kuchli parolni himoyalangan sozlamada belgilang.
  Superuser/Create roles/Create databases/Bypass RLS huquqlarini bermang.
  Bu rol migratsiya uchun o‘zi yaratadigan obyektlarda DDL huquqiga ega; admin emas.
- **Connect → Session pooler**, port **5432**. Runtime uchun ezo_app roli va dashboard
  ko‘rsatgan project suffiksini ishlating. Transaction pooler 6543 mos emas.
- Render DATABASE_URL namunasi:
  postgresql+psycopg://APP_USER_WITH_PROJECT_SUFFIX:PASSWORD@SESSION_HOST:5432/postgres?sslmode=verify-full&sslrootcert=system&connect_timeout=10
- Maxsus belgili parol URL-kodlangan bo‘lishi shart. Uni ommaviy encoder’ga bermang.
  Yangi loyiha uchun uzun harf/raqamli parol bu xatoni chetlab o‘tadi.
- Sertifikat xatosida TLS’ni o‘chirmang. Rasmiy Supabase SSL sozlamasidan project CA
  sertifikatini oling; Render **Environment → Secret Files** ga supabase-ca.crt sifatida
  qo‘shing. DSNda sslrootcert=/etc/secrets/supabase-ca.crt ishlating.
- Xatoda host, project suffiksi, port, parol va CA’ni tekshiring. To‘liq DSNni chatga
  yubormang. Oldingi bazada rol/egani almashtirish alohida review talab qiladi.

## 8. Render API va doimiy disk

- Manzil: https://dashboard.render.com → **New + → Blueprint → GitHub repository EZO**.
  Faqat tasdiqlangan commitdagi deploy/render-paid-reference.yamlni tanlang. Narxni tekshiring.
- Docker root: apps/api; Dockerfile: ./Dockerfile; bitta instance; disk:
  **/app/storage**, 10 GB; health: **/api/health**. Auto-deploy o‘chiq qolsin.
- Dastlab Standard; real RAMni kuzating. OCR/Office uchun bepul/512 MB hostga tayanmang.
- **Disks** da haqiqiy disk attachment ko‘rinsin. Startup diskni yoki yozish huquqini
  rad etsa ephemeral papkaga o‘tib ketmang. Diskni o‘chirish fayllarni yo‘qotadi.

## 9. Server-only maxfiy qiymatlar

- **Render service → Environment**. [Namuna](../deploy/private-beta.env.example)ni oching.
- EZO_ENV=production; EZO_AUTH_MODE=token; EZO_DEBUG_TRACES=false;
  EZO_FETCH_ALLOW_PRIVATE_NETWORKS=false; EZO_STORAGE_DIR=/app/storage;
  EZO_VECTOR_STORE=pgvector; DATABASE_URL — yuqoridagi TLS ulanishi.
- EZO_CORS_ORIGINS=https://FRONTEND_HOST — aniq HTTPS origin, yo‘l, oxirgi / yoki *siz.
- Blueprint EZO_API_TOKENni tasodifiy yaratadi. Uni xavfsiz saqlang; faqat EZO Settings’ga kiriting.
- AI uchun ANTHROPIC_API_KEY, OPENAI_API_KEY yoki GEMINI_API_KEYdan biri kerak.
  Kalitsiz offline xabar chiqishi AI javobi yoki AI testi muvaffaqiyati emas.
- Kalitlarni screenshot, GitHub, chat yoki NEXT_PUBLIC_* maydonlariga yozmang.
  Oshkor bo‘lsa providerda bekor qilib, yangi qiymatni himoyalangan maydonga qo‘ying.

## 10. Vercel frontend

- Manzil: https://vercel.com/new → **Import Git Repository → EZO → Configure Project**.
- Framework: Next.js; **Root Directory: apps/web**; root tashqarisidagi workspace
  fayllarini build’ga kiritish yoqilgan bo‘lsin.
- **Environment Variables:** EZO_API_URL=https://RENDER_API_HOST.
  Bu URL ommaviy; unda token bo‘lmasin. Vercel’ga AI kaliti, DATABASE_URL yoki owner token kiritmang.
- **Settings → Git → Production Branch:** claude/gifted-goodall-bpf01s.
  Production/Preview qiymatlarini ajrating; **Deployment Protection** bilan preview’ni himoyalang.
- HTTPS frontend domenini olgach Render CORS’ni yangilang. Barcha preview domenlariga
  ruxsat bermang. CORS/CSP xatosini xavfsizlikni o‘chirib tuzatmang.
- Faqat owner deployment va tarifni tasdiqlagach **Deploy** bosing.

## 11. Owner kirishini tekshirish

- Frontend HTTPS manzili → **Settings → API token**; Render tokenini shu yerga kiriting.
- Noto‘g‘ri/yo‘q token bilan shaxsiy chat, fayllar va status ochilmasin.
  To‘g‘ri token bilan ishlasin; /api/health esa token talab qilmaydi.
- Token shu brauzer profilida saqlanadi. Umumiy qurilmada ishlatmang va qolgan tokenni
  tozalang. Bu bir kishilik model; multi-user login yoki 2FA emas.

## 12. Chat, IELTS va taqdimot

- O‘zbekcha Salom, inglizcha va ruscha oddiy savol yuboring.
  Kalitli ulanishda haqiqiy javob, kalitsiz holatda aniq offline bildirishnoma kuting.
- IELTS mashqini boshlang, keyingi javob sessiyani davom ettirsin.
  Baholash rasmiy examiner sertifikati emas.
- Kichik taqdimot so‘rang, PPTX/PDFni oching. Tanlangan kutubxona bo‘lsa manba
  va citationlar shu doirani saqlasin.
- Xatoda amal nomi, vaqt va run/artifact IDni yozing; maxfiy hujjat mazmunini ulashmang.

## 13. Fayl yuklash va olish

- Chatdagi biriktirish yoki **Files** tugmasi orqali kichik, maxfiy bo‘lmagan TXT/DOCX/PDF yuklang.
- Fayl haqida savol bering, citationni oching; yaratilgan DOCX/XLSX/PPTX/PDFni yuklab oling.
  Telefon **Downloads / Files** ilovasida ochilsin.
- Hajm xatosida faylni kichraytiring; exe’ni pdf deb qayta nomlamang.
  Tashqi resursga bog‘langan Office fayli xavfsizlik sababli rad etilishi mumkin.

## 14. Saqlanishni tekshirish

- Test upload va artifact IDlarini saqlang; faol generatsiya tugashini kuting.
  **Render → service → Manual Deploy → Restart service**.
- Frontendni yangilang, eski fayl va artifact’ni yana oling; mazmun o‘zgarmasin.
- Fayl yo‘qolsa yangi yozuvlarni to‘xtating, **Disks / EZO_STORAGE_DIR**ni tekshiring.
  Diskni o‘chirmang yoki bo‘sh disk bilan almashtirmang.

## 15. Loglar va health

- **Render → service → Logs / Events**; **Vercel → project → Deployments → deployment → Logs**.
- https://API_HOST/api/health 200/ok; baza uzilganda 503. Health AI kaliti,
  backup yoki barcha tool ishlashini tasdiqlamaydi.
- Loglar redaksiyalangan bo‘lsa ham maxfiy: to‘liq DSN, kalit va fayl matnini ulashmang.
- Migratsiya xatosida stamp/downgrade, volume yoki bazani o‘chirishni taxmin bilan bajarmang;
  commit va xavfsiz xato nomini Codex/Claude review’iga bering.

## 16. Xarajat va backup

- Provider konsoli → **Billing / Usage / Limits**: oylik limit va alert.
  Ayrim budgetlar faqat ogohlantiradi; hard cap borligini tekshiring.
- Render/Supabase/Vercel usage alertlarini yoqing. EZO_RATE_LIMIT_CHAT_PER_DAY
  chat/voice limitidir, embeddings va barcha boshqa AI ishlariga universal dollar cap emas.
- Taxmin: Render Standard $25 + 10 GB disk ~$2.50; Supabase Pro ~$25;
  Vercel Hobby $0 yoki Pro ~$20/seat: ~$52.50–$72.50/oy. AI, egress, backup,
  soliq va overage alohida. Xariddan oldin tekshiring:
  https://render.com/pricing, https://supabase.com/pricing, https://vercel.com/pricing.
- **Supabase → Database → Backups**ni tekshiring. Bu Render fayllarini saqlamaydi.
  Yozuvlar to‘xtatilgan paytda mos baza+disk backup va alohida restore sinovi kerak.
  Telefon UI yetarli bo‘lmasa Codex’dan secure muhitda backup avtomatizatsiyasini
  tayyorlashni so‘rang; terminal ilovasi shart emas. Restore sinovisiz shaxsiy ma’lumot kiritmang.

## 17. Rollback

- Faol yozuvlarni to‘xtating, oldingi aniq commit va mos baza/disk backup IDlarini toping.
- **Render → Events / Manual Deploy → oldingi commit**;
  **Vercel → Deployments → oldingi tekshirilgan deployment → … → Instant Rollback**.
- Faqat sxema mos bo‘lsa eski image’ga qayting. Mos bo‘lmasa forward-fix yoki owner
  tasdiqlagan matched restore kerak. Restore oxirgi yozuvlarni yo‘qotishi mumkin.
- Xatoni “tuzatish” uchun production bazani/volume’ni o‘chirmang; ta’sirni review qiling.

## Yakuniy owner qarorlari

1. Ochiq native HIGH/CRITICAL xavflari bo‘yicha mustaqil review va aniq qaror.
2. PR/CI va Active ruleset; hosting to‘lovi va deployment’ga rozilik.
3. License/visibility: loyiha hozir public. Proprietary/private, MIT yoki Apache-2.0
   tanlovini faqat egasi qiladi; Codex LICENSE yoki visibility’ni o‘zgartirmaydi.
4. Real-host secretlar, mos backup va restore tasdiqlanmagan bo‘lsa loyiha
   **actually deployed** deb hisoblanmaydi.
