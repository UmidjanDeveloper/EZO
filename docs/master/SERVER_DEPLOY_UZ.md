# EZO’ni serverga joylash (o‘zbekcha qo‘llanma)

Bu qo‘llanma EZO’ni internetdagi o‘z serveringizda ishga tushirishni ko‘rsatadi. Hamma
narsa tayyorlangan, lekin **server, domen va pullik xizmatlarni faqat siz olasiz** — EZO
hech narsa sotib olmaydi. Batafsil arxitektura: `docs/deployment/EZO_INFRASTRUCTURE_ARCHITECTURE.md`,
har bir tashqi qadam va narxi: `docs/deployment/OWNER_ACTIVATION_CHECKLIST.md`.

## Nima kerak

| Narsa | Tavsiya | Taxminiy narx |
|---|---|---|
| Server | Hetzner CX23 yoki shunga o‘xshash: 2 vCPU, 4 GB RAM, Ubuntu 24.04 | ≈ €4–6/oy |
| Domen | Bor domeningizning ikki subdomeni: `ezo.…` va `api.ezo.…` | 0 (yoki ≈ $1/oy) |
| AI kaliti | Bitta provayder (masalan Gemini), konsolda **xarajat chegarasi** bilan | foydalanishga qarab |
| Zaxira (ixtiyoriy) | Cloudflare R2, 10 GB gacha | 0 |

## 1. Serverni tayyorlash (bir marta)

```bash
# Serverda (root yoki sudo bilan)
apt-get update && apt-get install -y docker.io docker-compose-v2 git age
git clone https://github.com/UmidjanDeveloper/EZO.git /opt/ezo   # yopiq repo: GitHub deploy key bilan
cd /opt/ezo/deploy/primary
cp primary.env.example primary.env
nano primary.env   # domenlar, EZO_OWNER_EMAIL, AI kaliti, ixtiyoriy Telegram/Eskiz
```

Xavfsizlik devori (firewall): faqat 22 (faqat sizning IP), 80 va 443 portlar ochiq bo‘lsin.

## 2. DNS

Domeningiz boshqaruvida ikkita **A** yozuv qo‘shing: `EZO_WEB_DOMAIN` va `EZO_API_DOMAIN` →
serverning IP manzili. HTTPS sertifikatini Caddy o‘zi oladi (Let’s Encrypt).

## 3. Ishga tushirish — bitta buyruq

```bash
cd /opt/ezo/deploy/primary
./deploy.sh
```

Skript: maxfiy parollar va kalitlarni **serverning o‘zida** yaratadi
(`secrets/compose.env`, Git’ga tushmaydi), konfiguratsiyani tekshiradi, ma’lumotlar bazasi,
API, web va Caddy’ni ishga tushiradi va manzillarni chiqaradi. Yangilash uchun:
`git pull && ./deploy.sh`.

Kirish: brauzerda `https://EZO_WEB_DOMAIN` → **Sozlamalar → API token** ga
`secrets/compose.env` dagi `EZO_API_TOKEN` ni kiriting (bu egasining kaliti). Xodimlarni
**Boshqaruv → Foydalanuvchilar → «Taklif havolasi»** orqali taklif qilasiz.

## 4. Avtomatik zaxira nusxa (har kecha)

```bash
# O‘Z kompyuteringizda (serverda emas!): kalit juftligini yarating
age-keygen -o ezo-backup-key.txt     # maxfiy kalit — offline saqlang
# Ekranda chiqqan "public key: age1..." ni serverga o‘rnating:
sudo /opt/ezo/deploy/primary/install-backup-timer.sh age1...
sudo systemctl start ezo-backup.service      # birinchi nusxani hozir oling
```

Server nusxani faqat shifrlay oladi, o‘qiy olmaydi. Nusxa haqiqiy ekanini tekshirish
(oyda bir marta va har yangilanishdan keyin), maxfiy kalit bor kompyuterda:
`./restore-check.sh backups/<eng yangi>.tar.age` — bo‘sh konteynerga tiklab, raqamlarni
ko‘rsatadi. Tekshiruvdan o‘tmagan nusxa — nusxa emas. Serverdan tashqariga (R2) yuborish:
`docs/deployment/BACKUP_RESTORE_PLAN.md`.

## Serverda nima ishlaydi va nima ishlamaydi

- **Ishlaydi:** chat, hujjatlar (Word/Excel/PDF yaratish), Devonxona, Tuman markazi,
  Jadval (fon vazifalari), LEX.UZ, Telegram bot, SMS (Eskiz), xodimlar hisoblari, talaffuz
  tekshiruvi (ovoz provayderi bilan), CSV tahlili.
- **Alohida xost kerak:** yuklangan PDF/DOCX/XLSX/skanlarni o‘qish va ko‘nikmalarni
  (o‘z kodini) ishga tushirish Docker soketini talab qiladi. Xavfsizlik uchun ular API
  serverida yoqilmaydi — alohida izolyatsiyalangan xostda ishlaydi
  (`docs/deployment/EXECUTOR_REQUIREMENTS.md`). O‘z kompyuteringizda esa
  `COMPOSE_PROFILES=documents,skills` bilan hammasi ishlaydi.
- **Kompyuterni boshqarish** server bilan ham ishlaydi: desktop ilovani serverga ulaysiz.
