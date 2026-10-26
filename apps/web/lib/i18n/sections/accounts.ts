/** Texts of the accounts surface. Uzbek is the reference; en and ru must have every key. */
const uz = {
  title: "Foydalanuvchilar va tokenlar",
  subtitle:
    "Hisoblarni faqat siz yaratasiz. Tarif (free/pro/premium) faqat kunlik limitni belgilaydi, hech qanday boshqaruv huquqini bermaydi. To‘lov ulanmagan.",
  secretAfterEmail:
    "uchun token. U faqat hozir ko‘rsatiladi — nusxa olib, foydalanuvchiga xavfsiz yo‘l bilan bering:",
  hide: "Yashirish",
  emailLabel: "Email",
  nameLabel: "Ism",
  tierLabel: "Tarif",
  add: "Qo‘shish",
  ownerUnlimited: "Egasi · cheklovsiz",
  tierOf: "{email} tarifi",
  disable: "O‘chirish",
  enable: "Yoqish",
  issueToken: "Token berish",
  tokens: "Tokenlar",
  tokenRevoked: "bekor qilingan",
  tokenExpires: "muddati: {date}",
  tokenNoExpiry: "cheksiz",
  tokenLastUsed: "oxirgi: {date}",
  revoke: "Bekor qilish",
};
export type Section = typeof uz;
const en: Section = {
  title: "Users and tokens",
  subtitle:
    "Only you create accounts. The tier (free/pro/premium) sets the daily limit only and grants no governance rights. Billing is not connected.",
  secretAfterEmail:
    "— token for this account. It is shown only now: copy it and hand it to the user over a secure channel:",
  hide: "Hide",
  emailLabel: "Email",
  nameLabel: "Name",
  tierLabel: "Tier",
  add: "Add",
  ownerUnlimited: "Owner · unlimited",
  tierOf: "Tier of {email}",
  disable: "Disable",
  enable: "Enable",
  issueToken: "Issue token",
  tokens: "Tokens",
  tokenRevoked: "revoked",
  tokenExpires: "expires: {date}",
  tokenNoExpiry: "never",
  tokenLastUsed: "last used: {date}",
  revoke: "Revoke",
};
const ru: Section = {
  title: "Пользователи и токены",
  subtitle:
    "Аккаунты создаёте только вы. Тариф (free/pro/premium) задаёт только дневной лимит и не даёт никаких прав управления. Оплата не подключена.",
  secretAfterEmail:
    "— токен для этого аккаунта. Он показывается только сейчас: скопируйте его и передайте пользователю безопасным способом:",
  hide: "Скрыть",
  emailLabel: "Email",
  nameLabel: "Имя",
  tierLabel: "Тариф",
  add: "Добавить",
  ownerUnlimited: "Владелец · без ограничений",
  tierOf: "Тариф {email}",
  disable: "Отключить",
  enable: "Включить",
  issueToken: "Выдать токен",
  tokens: "Токены",
  tokenRevoked: "отозван",
  tokenExpires: "срок: {date}",
  tokenNoExpiry: "бессрочно",
  tokenLastUsed: "последнее использование: {date}",
  revoke: "Отозвать",
};
export const accounts = { uz, en, ru };
