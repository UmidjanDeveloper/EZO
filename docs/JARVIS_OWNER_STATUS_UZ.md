# EZO JARVIS — egasi uchun haqiqiy holat

Bu to‘liq Windows/telefon Jarvis emas. Merge va deploy qilinmagan backend candidate.
Sakkizta upstream bo‘yicha holat: master/UPSTREAM_IMPLEMENTATION_MATRIX.md.

## Hozir ishlaydigan qismlar

- Authenticated API aniq berilgan sonlardan foiz hisoblaydi. `percent_change` va
  `percent_of` farq qiladi; metodni egasi tanlaydi. Masalan100→125 uchun25% o‘zgarish
  yoki125% ulush. Fayldan o‘qilgan, deb ko‘rsatilmaydi. Nol asos rad qilinadi.
- Hisob natijasining shaxsiy, DB’da saqlangan receipt’i bor. Unda hash/holat/vaqt
  metadata’si mavjud; u Telegram yuborildi yoki PDF yaratildi degani emas.
- Tool graph’ni tekshirish API’si haqiqiy registry/schema va mavjud DAG validatorni
  ishlatadi. Reja tekshirilishi — ruxsat yoki bajarilish emas.
- Linux’dagi alohida companion process owner tanlagan bitta katalogning bevosita
  regular fayllari metadata’sini o‘qiydi. Body o‘qimaydi, symlink/FIFO ochmaydi,
  parser/shell/model ishga tushirmaydi. Ed25519 signature, actor/device/task/root,
  qisqa deadline va restartdan keyingi replay/root identity tekshiriladi.

## Xavfsiz lokal tekshiruv

Repository’ning tayyor API development muhitida:

```sh
cd apps/api
.venv/bin/python -m pytest -q tests/integration/test_companion_metadata.py
```

Test haqiqiy vaqtinchalik katalog va alohida process bilan ishlaydi. Kalitlar faqat
shu test uchun vaqtinchalik; production kalit yaratilmaydi. Root/admin Linux process
rad qilinadi. Bu test Windows, Android yoki iPhone ishlayotganini isbotlamaydi.
Tasodifiy internet installer, `curl|bash`, `irm|iex` yoki model yuklash kerak emas.

API endpointlar va aniq JSON: integration/MASTER_API_CONTRACT.md.
Authenticated lokal instance bo‘lmasa, test orqali tekshiring; himoyani o‘chirmang.

## Hali tayyor bo‘lmagan joylar

| Funksiya | Holat |
|---|---|
| Windows Downloads | Native handle/DACL admission va haqiqiy Windows testlari yo‘q. Linux pathname tekshiruvi Windows o‘rniga ishlatilmaydi. |
| Avtomatik remote pairing | Hali yo‘q. Hozir controller public key va device konfiguratsiyasi owner tomonidan alohida pin qilinadi. Production enrollment UI/API deb ko‘rsatmang. |
| Ko‘p bosqichli durable task queue | Hali to‘liq emas; hisob receipt’i yoki lokal replay journal uni almashtirmaydi. |
| Chrome/Android/iOS | Antigravity UX va platform ruxsatlari bilan integratsiya kutilmoqda. Extension saytlarga ruxsat olishi OS fayllariga ruxsat emas. |
| OCR/DOCX/XLSX→PDF | Reviewed isolated worker va output-verification acceptance’i kerak; API process’da yoqilmaydi. |
| Telegram | Credential, recipient resolution, scoped/revocable approval va test-account delivery dalili yo‘q; yuborilgan, deb ko‘rsatilmaydi. |
| O‘zbekcha voice→action | Provider adapterlari bor, lekin real audio/qurilma E2E testi hali yo‘q. AI API ixtiyoriy; offline rejim soxta javob bermaydi. |
| Skill execution/K4 | Tekshirilgan VM/microVM trust boundary yo‘q. Draft/static pass generated code’ni ishga tushirishga ruxsat bermaydi. |

Metadata mtime bo‘yicha tartiblanadi: bu brauzer download vaqti emas. Teng vaqt yoki
1000-entry limit bo‘lsa, oxirgi faylni taxminan tanlamang. File ID ham read permission
emas. Filenames — ishonchsiz display data; UX ularni escape qilishi kerak.

$10 server budjeti, AI API xarajati alohida, hali tasdiqlangan full-stack4/8GB VM
benchmark va barcha disk/backup/tax narxlari bilan isbotlanmagan. Hozir hech qanday
servis, pullik reja, billing yoki production credential yaratilmagan. Public launch
ruxsat etilmagan. Independent security review va owner tasdig‘isiz merge/deploy yo‘q.
