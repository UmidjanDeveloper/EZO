# Owner-supplied EZO OS P0–P9 master roadmap

Source: `EZO_OS_Toliq_Ish_Reja_YANGI.docx`, supplied by the owner in this session.
Original SHA-256: `da633f288ca7e5296d3e9973fef7cba2b3859de260065c710d294d48b9235f53`.

This is a faithful plain-text extraction of the planning document, including its historical 19 October status claims. Those claims are not current verification. Table cells are preserved in document order. The owner states that further capabilities are not yet listed here; the eight upstream requirements, JARVIS/device mission, security controls and no-deploy/no-merge instructions from the session remain additional requirements.

---

LOYIHA KONSEPSIYASI  •  MASTER ROADMAP  •  V1.0
EZO OS
EZO — sen bilan o‘sadigan sun’iy intellekt.
EZO nima, qanday ishlashi kerak, qanday rivojlanadi va uni bosqichma-bosqich qanday quramiz?
HUJJAT MAQSADI
QAMROV
Yagona bosh reja
EZO’ning missiyasi, mahsulot modullari, xavfsizlik qoidalari va rivojlanish bosqichlarini bir joyga jamlash.
Ishlash usuli
Codex — ishlab chiqish va test; Claude — mustaqil review; loyiha egasi — qaror va tasdiq.
Hozirgi strategiya
Avval sifatli mahsulot; Vercel, Render, Supabase va haqiqiy API’lar — yakuniy integratsiya bosqichida.
Tuzilgan sana: 19-oktabr 2026-yil
Maqom: rejalashtirish hujjati. Rejadagi imkoniyatlar hozir ishlayotgan funksiya sifatida talqin qilinmaydi.
01  |  EZO nima?
EZO — o‘zbek tilini ustuvor qo‘llab-quvvatlaydigan, boshqa tillarda ham tabiiy muloqot qiladigan, foydalanuvchining roziligi bilan uning maqsadlari va afzalliklariga moslashadigan, turli vazifalar uchun AI agentlarni birlashtiruvchi shaxsiy yordamchi platforma.
EZO insondek ko‘rinishga urinmaydi: u do‘stona, samimiy, hazilkash va foydali AI hamroh bo‘ladi. U real insoniy munosabatlar o‘rnini egallamaydi; shaxsiy ma’lumot va foydalanuvchi nazorati birinchi o‘rinda turadi.
Missiya va mahsulot va’dasi
Har bir inson uchun alohida Personal EZO: shaxsiy xotira, maqsadlar, bilimlar, odatlar va ruxsatlar.
Vazifani tushunib, kerakli agentni avtomatik tanlash; foydalanuvchi agent nomini bilishi shart emas.
Kitob, sayt, hujjat va kutubxonalardan ruxsatli bilim olish; tahlil, manbali javob va amaliy yordam.
Til o‘rganish, IELTS speaking, taqdimot, hujjat, tadqiqot va kundalik ishlar uchun yagona tajriba.
Platformaning global rivojlanishi faqat Super Admin nazorati ostida amalga oshiriladi.
EZO qanday bo‘lmasligi kerak?
Shunchaki umumiy chatbot yoki faqat PDF qisqartiruvchi dastur bo‘lmasin.
Manbani o‘qishni modelning ichki vaznlarini qayta o‘qitish bilan adashtirmasin.
Ishonchsiz sayt matnini buyruq sifatida bajarmasin; dalilsiz “o‘rgandim” yoki “ishga tushirdim” demasin.
Obunachilar platforma kodini, global agentlarni yoki GitHub deploy jarayonini boshqarmasin.
Avtomatik merge, ruxsatsiz deploy, cheksiz xarajat yoki nazoratsiz kod bajarish bo‘lmasin.
Asosiy prinsip
“Har bir foydalanuvchining EZO’si shaxsiy bilim va moslashuv jihatidan rivojlanadi; umumiy EZO platformasini takomillashtirish vakolati faqat Super Admin’da bo‘ladi.”
02  |  EZO arxitekturasi: bitta platforma, shaxsiy tajribalar
QATLAM
VAZIFASI
EZO Core
Suhbat, vazifa rejalash, agentlar koordinatsiyasi, model/provider adapterlari, xatolarni boshqarish.
Personal Intelligence (K9)
Rozilikka asoslangan xotira, maqsadlar, afzalliklar, progress, shaxsiy agent tanlovi.
Agent Hub
Student, IELTS, Presentation, Documents, Research va keyinchalik qo‘shiladigan agentlar.
Knowledge OS (K1–K7)
Manba o‘qish, qidirish, iqtibos, qobiliyat tahlili, xavfsiz ko‘nikma yaratish va bilim yangilash.
Self-Improvement (K8)
Faqat Super Admin: platformadagi bo‘shliqni aniqlash, kod taklif qilish, izolyatsiyalangan sinov, PR.
Security & Permissions
Server-side rollar, ma’lumot ajratish, tasdiqlar, audit, limitlar, sirlarni himoya qilish.
Infrastructure (oxirida)
Vercel — UI; Render — Python API/agentlar va doimiy disk; Supabase — PostgreSQL/pgvector.
03  |  Asosiy mahsulot modullari
MODUL
KUTILGAN TAJRIBA
EZO Companion
O‘zbekcha ravon suhbat, foydalanuvchi ohangiga moslashish, muloyim hazil, halol chegaralar.
Personal Memory
Foydalanuvchi ruxsati bilan maqsad, loyiha, til, odat va afzalliklarni saqlash; ko‘rish/tuzatish/o‘chirish.
Smart Agent Router
“IELTS speaking qilaylik” → IELTS; “prezentatsiya tayyorla” → Presentation; “kitobni o‘rgan” → Student.
EZO Student
Kitoblar, saytlar, maqolalar va ruxsatli kutubxonalarni chuqur o‘rganish; dars, test, izoh, tahlil.
IELTS Examiner 2.0
Tabiiy speaking sessiyasi, tinglash, konstruktiv feedback, progress; rasmiy imtihonchi maqomini da’vo qilmaslik.
Presentation Maker 2.0
Professional PPTX, slayd tuzilishi, dizayn, manbali mazmun, tahrirlash va eksport.
Documents & Office
DOCX/XLSX/PPTX/PDF yaratish, tahrirlash, OCR, konvertatsiya va yuklab olish.
Research & Knowledge
Manbali izlanish, versiya/sana nazorati, qarama-qarshi ma’lumotlarni aniqlash.
Premium UX
Telefon va kompyuterda tez, qulay, tushunarli, bir xil sifatdagi interfeys.
04  |  EZO Student — Deep Knowledge & Personal Tutor
Maqsad: EZO berilgan manbalarni faqat qisqartirmasdan, ularning tuzilmasi, asosiy tushunchalari, dalillari, bog‘liqliklari va amaliy qo‘llanishini tahlil qilsin. Shu bilan birga foydalanuvchiga bilimni egallashga yordam bersin.
Qabul qilinadigan manbalar
Foydalanuvchi yuklagan PDF, EPUB, DOCX, ilmiy maqola, o‘quv materiallari va ruxsatli elektron kitoblar.
Ochiq va ruxsatli saytlar, hujjatlashtirish sahifalari, GitHub repozitoriylari, PyPI/npm hujjatlari.
Skan hujjatlar uchun OCR; matn, jadval, formula, bob va sahifa tuzilmasini imkon qadar saqlash.
Pullik, maxfiy yoki cheklangan kontentni ruxsatsiz olish va mualliflik huquqini chetlab o‘tish yo‘q.
Chuqur o‘rganish zanjiri
1. Manbani tekshirish: ruxsat, format, hajm, kelib chiqish, xavfsiz yuklash.
2. Strukturali o‘qish: bob, bo‘lim, ta’rif, misol, jadval, formula va sahifa manzili.
3. Bilimlarni indekslash: matn bo‘laklari, semantik qidiruv, metadata va manba versiyasi.
4. Tahlil: tushunchalar xaritasi, old shartlar, qarama-qarshiliklar, dalil kuchi.
5. Qo‘llash: manbali savol-javob, mashq, o‘quv reja, test, prezentatsiya va loyiha yordami.
6. Progress: foydalanuvchi xatolari va o‘zlashtirish darajasiga mos mashg‘ulotlar.
7. Yangilash: manba o‘zgarsa qayta tekshirish, eskirgan bilimni belgilash.
Student sifati uchun qat’iy talablar
Muhim xulosalarda manba, sahifa yoki bo‘lim ko‘rsatiladi (mavjud bo‘lsa).
Manbadan olingan fakt va EZO’ning taxmini alohida belgilanadi.
Bir-biriga zid manbalar yashirilmaydi; noaniqlik ochiq aytiladi.
Katta kitoblar bo‘lib-bo‘lib, resurs limiti va qayta davom ettiriladigan jarayon bilan o‘qiladi.
Shaxsiy kutubxona faqat egasiga tegishli; boshqa foydalanuvchi manbasiga kirish yo‘q.
O‘rganilgan ma’lumot Knowledge OS’da saqlanadi; modelning vaznlari avtomatik qayta o‘qitilmaydi.
Student V1 dan mukammal versiyagacha
BOSQICH
NATIJA
Student Deep Reading V1
Bob/bo‘lim-aware ingestion, manbali chat, sahifa/bo‘lim havolalari, study guide va oddiy test.
Student V2
Concept graph, bir nechta manbani taqqoslash, qarama-qarshilik va dalil sifati.
Student V3
Shaxsiy tutor, diagnostika, flashcard, spaced repetition, progress va individual learning path.
Student V4
O‘rganilgan bilimni boshqa agentlarga xavfsiz uzatish va amaliy loyihalarda qo‘llash.
05  |  Knowledge OS va Self-Improvement: K1–K9
BOSQICH
MAZMUN
HOLAT / QOIDA
K1
Ruxsatli manbalarni o‘qish va bilim kutubxonasiga kiritish.
Mavjud kod; chuqur QA kerak.
K2
Kutubxona doirasida qidiruv, chat va manbali javob.
Mavjud kod; scope QA kerak.
K3
Yangi imkoniyatlarni tahlil qilish va taklif tayyorlash.
Proposal-only; kod bajarmaydi.
K4
Alohida, izolyatsiyalangan va resurslari cheklangan sandbox.
Rejada; avval xavfsizlik dizayni.
K5
Skill Builder: yangi modul loyihasi va kod taklifi.
Rejada; faqat sandboxda sinov.
K6
Approval & GitHub: branch → test → PR → admin tasdig‘i.
Rejada; auto-merge yo‘q.
K7
Knowledge Refresh: versiya va manba yangilanishini tekshirish.
Rejada; ruxsat va limit bilan.
K8
Self-Improvement Engine: platforma kamchiliklarini aniqlash, yaxshilanishni taklif etish.
FAQAT SUPER ADMIN.
K9
Personal Intelligence: shaxsiy xotira, agent routing, moslashuv va maqsadlar.
Barcha foydalanuvchilarga shaxsiy scope.
Izoh: K1–K3 uchun dastlabki implementatsiya mavjudligi ma’lum; ularning barcha vaziyatlarda to‘liq ishlashi va live deploy holati tasdiqlangan deb hisoblanmaydi.
06  |  Super Admin va obunachilar: qat’iy vakolat chegarasi
EZO dastlab bitta egali Private Beta. Kelajakdagi Free/Pro/Premium obuna modeli uchun rollar hozirdanoq to‘g‘ri loyihalanadi, ammo ko‘p foydalanuvchili tizim tayyor deb e’lon qilinmaydi.
IMKONIYAT
FREE
PRO / PREMIUM
SUPER ADMIN
Shaxsiy suhbat va agentlar
Cheklangan
Kengaytirilgan
To‘liq
Shaxsiy xotira va moslashuv
Tarif bo‘yicha
Ha
Ha
Shaxsiy Student kutubxonasi
Limit bilan
Ha
Ha
Shaxsiy progress va o‘quv rejasi
Limit bilan
Ha
Ha
Global agentlar konfiguratsiyasi
Yo‘q
Yo‘q
Ha
K8 Self-Improvement
Yo‘q
Yo‘q
Ha
Platforma kodi / GitHub PR
Yo‘q
Yo‘q
Faqat tasdiq bilan
Production merge / deploy
Yo‘q
Yo‘q
Alohida tasdiq bilan
Ruxsatlar qanday himoyalanadi?
Server-side RBAC va resursga egalik tekshiruvi; tugmani yashirish xavfsizlik chorasi hisoblanmaydi.
Super Admin huquqi obuna to‘lovi bilan olinmaydi; alohida himoyalangan identifikatsiya va kuchli autentifikatsiya.
Har bir foydalanuvchining chatlari, fayllari, xotirasi, kutubxonasi va sozlamalari qat’iy ajratiladi.
GitHub va AI API sirli kalitlari faqat backendda saqlanadi; frontend yoki oddiy foydalanuvchiga uzatilmaydi.
Admin ham PR’ni avtomatik merge qilmaydi; tekshiruv, audit va kerakli tasdiqlar saqlanadi.
Global boshqaruv boshqa foydalanuvchilarning shaxsiy suhbatlarini cheksiz ko‘rish huquqini bermaydi.
Shaxsiy rivojlanish va platforma rivojlanishi
SHAXSIY EZO
GLOBAL EZO
Foydalanuvchi nimani o‘rganayotganini eslaydi, ruxsatli bilimni qo‘llaydi, agentlarni tanlaydi.
Yangi agent yoki platforma moduli ishlab chiqish faqat Super Admin workflow’ida.
Shaxsiy xotira va bilimlar boshqa akkauntga ko‘chmaydi.
Kodni o‘zgartirish: izolyatsiya → test → PR → mustaqil review → egasi tasdig‘i.
Foydalanuvchi o‘z ma’lumotini ko‘rishi, tuzatishi va o‘chirishi mumkin.
Har bir o‘zgarish auditda qayd etiladi; production ruxsatsiz yangilanmaydi.
07  |  Agentlar birga qanday ishlaydi?
EZO foydalanuvchi niyatini aniqlaydi, kerakli agent(lar)ni tanlaydi, ruxsatlarni tekshiradi va natijani yagona suhbatga qaytaradi. Agentlar mustaqil ravishda foydalanuvchi ma’lumotlari doirasidan chiqmaydi.
Namunaviy holat
Foydalanuvchi: “Python’ni o‘rganib, IELTS speaking’ni yaxshilamoqchiman; keyin loyiham uchun prezentatsiya tayyorlaymiz.”
Personal Intelligence: foydalanuvchi maqsadini tushunadi; rozilik bo‘lsa saqlaydi.
Student: Python bo‘yicha manbalar va shaxsiy o‘quv yo‘lini tayyorlaydi.
IELTS Agent: speaking sessiyasini olib boradi va feedback beradi.
Presentation Agent: foydalanuvchi so‘raganda loyihaga mos taqdimot yaratadi.
Orchestrator: natijalarni birlashtiradi, lekin ruxsatsiz tashqi amal bajarmaydi.
08  |  Bosqichma-bosqich ish rejasi
Muddatlar qat’iy sanalar emas. Har bir bosqich test va mustaqil review bilan yakunlanadi. Bir bosqichning “tayyor” deb belgilanishi uning qabul mezonlari bajarilganini anglatadi.
P0 — Baseline va xavfsizlik   |   Eng yuqori
Ish: Mavjud K1–K3, auth, agent routing, Docker va Office funksiyalarini qayta tekshirish; qoldiq CVE risklarini baholash.
Qabul mezoni: CI yashil, xavflar reyestri, aniq regressiya testlari, noaniq xavflar ochiq qayd etilgan.
P1 — Student Deep Reading V1   |   Eng yuqori
Ish: Uzun kitoblar, bob/bo‘lim indekslash, sahifali iqtibos, study guide va oddiy test.
Qabul mezoni: Ruxsatli PDF/EPUB/DOCX namunalarida manbali javob; resurs limitlari va ownership testlari.
P2 — Personal Intelligence K9   |   Yuqori
Ish: Rozilikli xotira, profil, maqsadlar, agent router, foydalanuvchi sozlamalari.
Qabul mezoni: Xotirani ko‘rish/o‘chirish, noto‘g‘ri routing regressiyasi, ma’lumotlar ajratilishi.
P3 — Student V2/V3   |   Yuqori
Ish: Concept map, manbalararo tahlil, shaxsiy tutor, progress, spaced repetition.
Qabul mezoni: Dalil va taxmin ajratilgan; progress real testlarda tekshirilgan.
P4 — K4 Secure Sandbox   |   Yuqori
Ish: Izolyatsiyalangan kod sinov arxitekturasi, resurs va tarmoq chegaralari, audit.
Qabul mezoni: Asosiy API’dan alohida, ruxsatsiz kirish/chiqish testlari; tashqi kodga to‘g‘ridan-to‘g‘ri yo‘l yo‘q.
P5 — K5/K6/K8 Admin Engine   |   Yuqori
Ish: Skill Builder, Self-Improvement, GitHub PR va approval flow.
Qabul mezoni: Faqat Super Admin; auto-merge/deploy yo‘q; audit va testlar bor.
P6 — K7 Knowledge Refresh   |   O‘rta
Ish: Manbalarni versiya va ruxsat asosida rejalashtirib yangilash.
Qabul mezoni: Yangilanish tarixchasi, eskirgan bilim belgisi, crawl limitlari.
P7 — IELTS / Presentation / Office 2.0   |   Yuqori
Ish: Speaking feedback, professional slaydlar, hujjat sifatini oshirish.
Qabul mezoni: E2E namunalar, sifat mezonlari, regressiya testlari.
P8 — Premium UI/UX va multi-user readiness   |   Yuqori
Ish: Mobil UX, accessibility, tarif/limitlar dizayni, RBAC va izolyatsiya.
Qabul mezoni: Telefon va desktop E2E; rol testlari; real foydalanuvchi ma’lumotlari ajratilgan.
P9 — Yakuniy cloud integratsiya   |   Oxirgi
Ish: Vercel + Render + Supabase + AI API; monitoring, backup, to‘lov, xavfsiz release.
Qabul mezoni: Live end-to-end sinov, rollback, limitlar, egasi tasdig‘i; shundan keyin launch.
09  |  Ishlab chiqish tartibi: Codex + Claude + egasi
ISHTIROKCHI
MAS’ULIYAT
CHEGARA
Codex
Kod, test, migration, dokumentatsiya, feature branch va PR.
Asosiy branchga bevosita commit, ruxsatsiz merge yoki deploy yo‘q.
Claude
Mustaqil architecture/security review, regressiya va integratsiya xatolarini aniqlash.
Kelishilgan review bosqichida kodni o‘zgartirmaydi.
Loyiha egasi
Talab, ustuvorlik, mahsulot qarori, PR va xarajat tasdig‘i.
GitHub/prod sirlarini chatga yubormaydi; yakuniy nazoratni saqlaydi.
Har bir feature uchun standart workflow
Talab va qabul mezonini 5–10 satrda yozish.
Codex eng yangi remote HEAD’dan alohida branch ochishi.
Kichik, mantiqiy commitlar va regressiya testlarini yozish.
GitHub CI: API, Web, Docker, secret va xavfsizlik tekshiruvlari.
Claude mustaqil ravishda PR’ni tekshirishi; topilmalar yopilishi.
Egasi PR’ni tasdiqlashi; faqat shundan keyin merge.
Yangi imkoniyatni roadmap va status hujjatida yangilash.
Bitta qoida — ko‘p xatoni oldini oladi
Yangi imkoniyat faqat “kod yozildi” bilan tayyor bo‘lmaydi. U test, xavfsizlik, mavjud agentlar bilan moslik, foydalanuvchi tajribasi va hujjatlashtirishdan o‘tganda tayyor hisoblanadi.
10  |  Sifat, maxfiylik va xavfsizlik standartlari
Ishonchsiz veb-sahifa, README, kitob yoki PDF matni model uchun ma’lumot; tizim buyrug‘i emas.
Tashqi saytga murojaat SSRF himoyasi, ruxsat, domen/URL siyosati va resurs limiti bilan amalga oshiriladi.
OCR/Office fayllari uchun hajm, vaqt, xotira, format va izolyatsiya cheklovlari bo‘ladi.
Super Admin huquqlari backendda tekshiriladi; GitHub tokenlari faqat himoyalangan server muhitida.
Har bir foydalanuvchi uchun xotira, kutubxona, fayl va chatlar alohida; o‘chirish/tuzatish huquqi mavjud.
AI xato qilishi mumkin: manba, dalil kuchi, noaniqlik va foydalanuvchi tasdig‘i muhim.
Xarajatlar: token limiti, kunlik kvota, foydalanish monitoringi va favqulodda o‘chirish imkoniyati.
Sog‘liq, huquq va boshqa yuqori xavfli mavzularda mutaxassis o‘rnini egallash da’vosi yo‘q.
Hozirgi ma’lum texnik holat — ehtiyotkor xulosa
2026-yil 19-oktabr holatidagi oldingi tekshiruvda integration branch HEAD 422beab, CI #84 va Security #12 muvaffaqiyatli yakunlangan. Bu live deployment emas. Docker API image bo‘yicha avval 79 ta HIGH va 1 ta CRITICAL OS paket zaifligi qayd etilgan; skaner yashil bo‘lsa ham qoldiq risk alohida tekshiriladi.
Repo: https://github.com/UmidjanDeveloper/EZO  |  Integration branch: claude/gifted-goodall-bpf01s
11  |  Cloud integratsiya: hozir emas, tayyor bo‘lganda
XIZMAT
NIMA UCHUN
QACHON
Vercel
Next.js web interfeys va preview.
Yakuniy launch bosqichida.
Render
FastAPI agentlar, OCR, LibreOffice, doimiy ishlaydigan backend va fayl diski.
Yakuniy launch bosqichida.
Supabase
PostgreSQL/pgvector, chat, xotira, bilim metadata va boshqa strukturali ma’lumotlar.
Yakuniy launch bosqichida.
AI API provayderlari
Haqiqiy til modeli, embeddings va boshqa AI imkoniyatlari.
Sifat/xarajat sinovidan keyin.
Hozir: local testlar, mock providerlar, Docker va GitHub CI. Kelajakda: xavfsiz branch protection, tasdiqlangan PR’dan keyingi avtomatik deployment, backup, monitoring, xarajat nazorati. Pullik resurs yoki production kalitlari egasining alohida roziligisiz yoqilmaydi.
12  |  Ertaga davom ettirish uchun tezkor cheklist
BIRINCHI 30–60 DAQIQADA
☐  GitHub’da EZO repository va eng so‘nggi branch/PR holatini tekshir.
☐  Codex’dan: “Hozirgi statusni tekshir, bitta eng foydali keyingi milestone’ni taklif qil” deb so‘ra.
☐  Claude’dan yangi PR uchun mustaqil security va architecture review so‘ra.
☐  P0 xavfsizlik qarzlari va P1 Student Deep Reading V1 bo‘yicha qaysi ish boshlanishini tanla.
☐  Yangi ishda K8 faqat Super Admin ekanini va cloud deploy hozir taqiqlanganini eslat.
Keyingi topshiriq uchun Codex’ga qisqa kontekst
“EZO OS — o‘zbekcha AI hamroh va agent platformasi. EZO Student kitob/saytlarni chuqur o‘rganadi; K1–K3 mavjud, K4–K9 rejada. K8 Self-Improvement faqat Super Admin uchun; boshqa foydalanuvchilar faqat shaxsiy bilim va agentlardan foydalanadi. Personal Memory, Agent Router, IELTS, Presentation, Documents va premium UX muhim. Hozir cloud deploy yo‘q. Latest HEAD’ni tekshir, mavjud kodni buzma, bitta milestone uchun branch + test + PR tayyorla, merge qilma.”
Claude’ga review topshirig‘i
“EZO’ning so‘nggi Codex PR’ini faqat read-only tekshir: xavfsizlik, regressiya, tenant isolation, admin-only Self-Improvement, manbalar trust boundary, test sifati, deploymentga tasodifiy o‘zgarishlar. Kamchiliklarni fayl/satr, xavf va aniq yechim bilan yoz. Commit, merge yoki deploy qilma.”
Hali hal qilinadigan mahsulot qarorlari
EZO Student’ning birinchi chiqariladigan formatlari va namunaviy kitoblar to‘plami.
Shaxsiy xotirada nimalar avtomatik emas, faqat rozilik bilan saqlanishi.
Free/Pro/Premium tarif limitlari — ko‘p foydalanuvchili arxitektura tayyor bo‘lgach.
GitHub repository litsenziyasi va kelajakda kodni ochiq/yopiq saqlash siyosati.
Self-Improvement sandbox xarajatlari, huquqlari va tasdiqlash interfeysi.
Cloud xizmatlari, AI provayderlari, byudjet va live release sanasi — keyinroq.
Bir jumlalik eslatma
EZO — foydalanuvchini tushunadigan, o‘rganuvchi, moslashuvchi va agentlar bilan yordam beruvchi shaxsiy AI; uning global kodini rivojlantirish esa faqat Super Admin nazoratidagi xavfsiz, tekshiriladigan jarayondir.
Hujjat yakuni • EZO OS strategik ish rejasi • 19.10.2026