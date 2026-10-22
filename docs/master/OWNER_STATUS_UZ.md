# Master candidate — egasi uchun holat

**To‘liq EZO OS hali tayyor emas. Deploy, merge yoki server sotib olish bajarilmadi.**
PR21 o‘zgarishlari saqlandi. Yangi branch uning ustida qurilgan; bu PR21’ni merge
qilish yoki mustaqil reviewni chetlab o‘tish emas.

Hozir backendda foydalanish mumkin bo‘lgan yangi qismlar:

- 2–4 ta o‘zingizga tegishli manbani iqtibos bilan taqqoslash;
- aniq matn daliliga bog‘langan konsept grafigi taklifi;
- AI taklif qilgan kartani alohida saqlash, eslashni belgilash va keyingi mashq vaqti;
- haqiqiy review sonlari; bu imtihon bahosi yoki bilim darajasi emas;
- Super Admin uchun o‘zgarmas capability taklifi va aynan o‘sha hashga review qarori.

Yangi ekranlar Antigravity bilan API kontrakti bo‘yicha ulanishi kerak. Frontend
fayllari o‘zgartirilmadi. Hozir UI’da hali yo‘q funksiyani tayyor ekran deb hisoblamang.

Nimani yoqish mumkin emas:

- umumiy AI kodini mavjud hujjat parserida ishga tushirish;
- sandboxsiz skill o‘rnatish yoki agentga shell/GitHub/secret huquqini berish;
- API ichida OCR yoki LibreOffice’ni production fallback sifatida yoqish;
- yangi natijalarni haqiqiy AI sifati yoki $10 server benchmarki deb ko‘rsatish.

To‘liq ishga tushirishdan oldin: master roadmapning P0–P9 ta’riflari bilan mapping,
Antigravity integratsiyasi, mustaqil kod/security review, K4 containment sinovi,
OCR/Office protocoli, haqiqiy provider sifati, backup qayta tiklash va real4/8GB VM
sinovlari yakunlanishi kerak. Bular uchun yashirin xavfsiz bo‘lmagan fallback yo‘q.

0019 additive migration. App rollback’da avvalgi image’ga qaytish yangi jadvallarni
saqlashi mumkin; kartalar/review tarixini yo‘qotadigan downgrade’ni avtomatik qilmang.
Migrationdan oldin DB va artifact backup oling, nusxada restore sinovini bajaring.
Full production profil endi migrationdan avval administrator DB rolini rad etadi;
alohida cheklangan app rolini oldingi setup qo‘llanmasi bo‘yicha tayyorlash kerak.

Server byudjeti: compute + disk + IP + trafik + offsite backup + soliq jami $10/oy.
AI xarajati alohida. Hozir tekshirilgan ikki host narxi va benchmarki yo‘q; to‘liq
native stack shu summaga sig‘adi deb va’da berilmaydi. Pulli xizmat faollashtirilmadi.
