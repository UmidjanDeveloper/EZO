# EZO to‘liq owner beta — egasi uchun yo‘riqnoma

**Hozir deploy qilishga ruxsat yo‘q.** Avval PR, mustaqil review, haqiqiy hosting
narxi va 4/8 GB VM sinovlari tasdiqlanishi kerak. Hozirgi status: **BLOCKED**.
Serverlar uchun oylik jami limit $10; AI xizmatlari xarajati alohida.
[Imkoniyatlar va xarajatlar jadvali](FULL_OWNER_BETA.md),
[tekshiruv dalillari](FULL_OWNER_BETA_VALIDATION.md).

## 1. Xarajatni tekshiring — hech narsa sotib olmang

VPS ekranida compute, disk, IPv4, trafik, backup, soliq va valyuta komissiyasini
alohida yozing. Jami $10 dan oshmasin. Hozirgi narx saytlari muhitdan 403 qaytardi;
hujjatdagi $9/$12.60 misollar narx taklifi emas. Oracle Always Free mavjudligi,
region sig‘imi, kartani tekshirish va idle/reclamation qoidalari ham tasdiqlanmagan.
Google trial doimiy bepul server emas; avtomatik pulli rejimga o‘tmang.

Native Student uchun ikkinchi **alohida executor host** kerak. Agar tekshirilgan
bepul host topilmasa, $10 ichida to‘liq native imkoniyat bor deb hisoblamang.
OCR va Office PDF’ni xavfsiz worker bilan ulash hali tugallanmagan. Ko‘proq RAM
bu yetishmayotgan implementatsiyani o‘zi yaratmaydi.

## 2. Egasi alohida ruxsat bergandan keyingi server tayyorlash

- Primary: Linux x86_64, Docker/cgroup v2, haqiqiy persistent disk, off-host backup.
  API, web, PG/pgvector va stored-text consumer shu yerda. Build’larni CI’da qiling.
- Executor: alohida host, Docker/cgroup v2, native parserdan tashqarida trusted
  controller. API konteyneriga Docker socket bermang. ARM Oracle tanlansa,
  shu arxitektura uchun image’larni qayta build/test qilish kerak.
- Owner telefoni uchun VPN + HTTPS/private ingress tayyorlang. DB, Docker va API
  portlarini internetga ochmang. TLS, firewall va haqiqiy private kirish sinovini
  bajarmasdan shaxsiy fayl yuklamang. Domen/sertifikatning takroriy xarajati ham hisobga olinadi.
- Kompyuteringizda lokal LLM, VoiceStudio yoki og‘ir OCR stack ishga tushirish shart emas.
  Implementatsiyadagi cloud adapterlar tashqi xizmatlardan foydalanadi; ularning
  sifati, ruxsati va narxi alohida tekshiriladi.

## 3. PostgreSQL va fayllar

0018 gacha Alembic migration ishlashi kerak. Administrator DB credentialini API’ga
bermang. Mavjud [cheklangan rol skripti](../deploy/supabase-private-beta-role.sql)
Supabase uchun; o‘z PG serveringizda unga teng, alohida tekshirilgan rol/grantlar
kerak. `anon`/`authenticated` uchun tasodifiy public table/column grantlar bo‘lmasin.
Connection URL’da `sslmode=verify-full`, tekshiriladigan hostname va ishonchli CA
bo‘lsin; xatoni yo‘qotish uchun `require` yoki TLS-off qo‘ymang.

Full profile hozir **local persistent StorageProvider** ishlatadi. API image’dagi
`/app/storage`ga haqiqiy disk/volume ulang; tmpfs yoki restartda yo‘qoladigan disk
ishlatmang. Supabase adapteri faqat oldingi kamaytirilgan free-beta profil uchun
review qilingan — full profilga majburlab yoqmang. Eski fayllar avtomatik ko‘chmaydi.
Student raw revision’lari PostgreSQL’da saqlanadi; backup ularni ham qamrasin.

## 4. Backend sozlamalari va API kalitlari

[full-owner.env.example](../deploy/full-owner.env.example) nomlarini backend secret
sozlamalariga kiriting. Fayldagi bo‘sh maydonlar haqiqiy credential emas. Ushbu ish
davomida yangi token yoki kalit yaratilmagan. Frontendga faqat API origin kerak;
OpenAI/Gemini/ElevenLabs, owner token va DB URL’ni `NEXT_PUBLIC_*`ga yozmang.

- `EZO_DEPLOYMENT_PROFILE=full`: Student, Personal, IELTS, Presentation, Office va
  barcha mavjud product route’lar saqlanadi. Bu yetishmayotgan funksiyani tayyor qilmaydi.
- Gemini/OpenAI adapterlari mavjud. Claude ixtiyoriy. `config/models.toml`dagi model
  ID’lari aynan sizning hisobingizda mavjudligini kelajakdagi ruxsatli sinovda tekshiring.
- ElevenLabs: `ELEVENLABS_API_KEY`; TTS uchun qo‘shimcha `EZO_ELEVENLABS_VOICE_ID`.
  Voice’ni ishlatishga huquqingiz bo‘lsin. Defaults: `scribe_v1` va
  `eleven_multilingual_v2`; mavjudligi live tekshirilmagan. Default TTS faqat en/ru
  uchun ruxsatlangan. Uzbek qo‘llovi tasdiqlanmaguncha `uz`ni ro‘yxatga qo‘shmang;
  OpenAI fallback tartibi ochiq ko‘rsatilgan.
- Vendor dashboard’da hard spend/key cheklovlarini o‘rnating. App’dagi kunlik limit
  restartda yangilanadi; SDK retry, image/search va boshqa processlar qo‘shimcha
  xarajat qilishi mumkin. Alert’ning o‘zi hard limit emas.
- Provider xatosi yoki quota bo‘lmasa, natija “haqiqiy AI javobi” deb ko‘rsatilmasin.
  IELTS text practice ball/talaffuz bahosini o‘ylab topmaydi; null natija — haqiqiy holat.
  Alohida IELTS ekranining voice adapteri hali fallback stub: global voice API
  mavjudligi to‘liq ovozli IELTS imtihoni ulanganini anglatmaydi.

## 5. Super Admin — faqat offline operator amali

Avval owner oddiy autentifikatsiya bilan `/api/me`ga kirib account yaratadi.
Keyin faqat ruxsatli operator, backendning private environment’ida:

```bash
python -m ezo_api.owner_admin --owner-email owner@example.com --grant --ack-owner-role-change
```

Email `EZO_OWNER_EMAIL` bilan bir xil bo‘lishi shart. Buyruq yangi user yaratmaydi,
subscription’ni admin qilmaydi, API tokenini almashtirmaydi. Bekor qilish:

```bash
python -m ezo_api.owner_admin --owner-email owner@example.com --revoke --ack-owner-role-change
```

`GET /api/admin/governance/status`: oddiy user403, Super Admin200. Shu role consent,
fayl egasi, worker isolation yoki budgetni chetlab o‘tmaydi. Admin panelning hali
yozilmagan qismlari va autonomous deploy/merge funksiyalari mavjud emas.

## 6. Student worker — API ichida emas

Primary hostda stored-text consumer mavjud CLI orqali alohida process bo‘ladi:

```bash
python -m ezo_api.knowledge.jobs.worker --worker-id owner-text-1
```

Dedicated executor hostda faqat oldindan build qilingan va tekshirilgan immutable
image ID bilan, private DB muhitida:

```bash
python -m ezo_api.student.worker --worker-id owner-native-1 --image sha256:REVIEWED_IMAGE_ID --ack-dedicated-executor-host
```

Misoldagi ID haqiqiy emas — o‘zingiz tekshirgan image ID kerak. Parallel native
worker ko‘paytirmang: bitta daemon uchun bitta slot. Network-none, read-only,
25s deadline, 768MiB limit, swap0 va PID/UID tekshiruvlarini olib tashlamang.
Scanned PDF uchun OCR bu protokolda yo‘q; LibreOffice’ni API’ga o‘rnatish yechim emas.

## 7. Haqiqiy 4/8 GB benchmark va qabul sinovi

Hozir bu sessiyada 4/8 GB VM yo‘q. [Benchmark protokoli](FULL_OWNER_BETA_BENCHMARKS.md)
bo‘yicha alohida ruxsatdan so‘ng sinov o‘tkazing. Docker xotira limiti VM sinovi emas.
Birinchi dataset shaxsiy bo‘lmasin. Owner auth/CORS, barcha product route’lar,
manual/consented memory, haqiqiy citation, DOCX/XLSX/PPTX download, provider
xatosi/quota, native timeout/cancel/OOM hamda restartdan keyingi fayllar tekshirilsin.

## 8. Backup va rollback

Yozuvlarni to‘xtatib, PostgreSQL dump va fayllarning mos snapshot/manifestini shifrlab
boshqa joyga saqlang. DB backup ichida local artifact baytlari yo‘q. Hash tekshiruvi
bilan ikkalasini alohida test muhitiga tiklang. Backup narxi va retention limitga
sig‘masa, launch BLOCKED qoladi. Hech qachon yagona backupni o‘chirmang.

Release SHA va image digestlarini saqlang. Rollback faqat schema mos bo‘lsa eski
image’ga; aks holda reviewed forward-fix yoki alohida ruxsatli matched restore.
0018ni ko‘r-ko‘rona downgrade qilish goals/roles ma’lumotlarini yo‘qotishi mumkin.
Keyingi deploy/merge uchun ham egasining alohida ruxsati kerak.
