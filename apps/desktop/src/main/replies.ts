/**
 * The desktop assistant's own replies in EZO's three languages. EZO answers in the
 * language you spoke: the language the server heard, or (typed text) a quick guess.
 */
import type { AppId, VolumeChange } from "./intents";

export type Lang = "uz" | "en" | "ru";

const UZ_CYRILLIC = /[ўқғҳ]/i;
const EN_WORDS = /(?<!\p{L})(the|open|find|type|write|turn|volume|please|my|screen|what|explain|file|up|down|mute|calculator|notepad|explorer|first|second|third)(?!\p{L})/iu;
const UZ_HINTS = /(o['‘’ʻ]|g['‘’ʻ]|(?<!\p{L})(och|top|yoz|ovoz|ekran|nima|qil|ber|ni|ga)(?!\p{L})|ni(?!\p{L})|[qx])/iu;

/** A small offline guess for typed commands; the server's detection is used for speech. */
export function guessLanguage(text: string): Lang {
  const letters = text.replace(/[^\p{L}]/gu, "");
  if (!letters) return "uz";
  const cyrillic = letters.replace(/[^Ѐ-ӿ]/g, "").length;
  if (cyrillic / letters.length > 0.5) return UZ_CYRILLIC.test(text) ? "uz" : "ru";
  if (EN_WORDS.test(text) && !UZ_HINTS.test(text)) return "en";
  return "uz";
}

const APP_NAMES: Record<Lang, Record<AppId, string>> = {
  uz: { calculator: "Kalkulyator", notepad: "Bloknot", paint: "Paint", explorer: "Fayl menejeri" },
  en: { calculator: "Calculator", notepad: "Notepad", paint: "Paint", explorer: "File Explorer" },
  ru: { calculator: "Калькулятор", notepad: "Блокнот", paint: "Paint", explorer: "Проводник" },
};

const TEXT = {
  uz: {
    needPermission: "Bu amal uchun ruxsat berilmagan. EZO sozlamalarida yoqing.",
    opened: (name: string) => `${name} ochildi.`,
    volume: { up: "Ovoz balandlatildi.", down: "Ovoz pasaytirildi.", mute: "Ovoz o‘chirildi/yoqildi." } as Record<VolumeChange, string>,
    typed: "Matn faol oynaga yozildi.",
    addFolder: "Avval sozlamalarda qidirish mumkin bo‘lgan papkani qo‘shing.",
    notFound: (q: string) => `“${q}” nomli fayl ruxsat berilgan papkalarda topilmadi.`,
    found: (n: number, list: string) => `${n} ta fayl topildi:\n${list}\nOchish uchun “birinchisini och” deng.`,
    searchFirst: "Avval faylni qidiring.",
    outside: "Bu fayl ruxsat berilgan papkalardan tashqarida.",
    fileOpened: (name: string) => `“${name}” ochildi.`,
    screenConfirm: "EZO hozir ekraningiz rasmini olib, tahlil uchun EZO serveriga yuboradi. Davom etilsinmi?",
    cancelled: "Bekor qilindi. Ekran rasmi olinmadi.",
    jarvisNotPaired: "Bu kompyuter JARVIS’ga ulanmagan. Sozlamalar → JARVIS bo‘limida ulang va papkani tanlang.",
    jarvisStarted: "Vazifa boshlandi. Fayllarni yuborishdan va Telegram’ga jo‘natishdan oldin sizdan so‘rayman.",
  },
  en: {
    needPermission: "This action is not allowed yet. Turn it on in EZO settings.",
    opened: (name: string) => `${name} is open.`,
    volume: { up: "Volume up.", down: "Volume down.", mute: "Sound muted/unmuted." } as Record<VolumeChange, string>,
    typed: "The text was typed into the active window.",
    addFolder: "First add a folder EZO may search, in settings.",
    notFound: (q: string) => `No file named “${q}” in the allowed folders.`,
    found: (n: number, list: string) => `Found ${n} files:\n${list}\nSay “open the first one” to open it.`,
    searchFirst: "Search for a file first.",
    outside: "This file is outside the allowed folders.",
    fileOpened: (name: string) => `Opened “${name}”.`,
    screenConfirm: "EZO will take a screenshot now and send it to the EZO server for analysis. Continue?",
    cancelled: "Cancelled. No screenshot was taken.",
    jarvisNotPaired: "This computer is not paired with JARVIS. Pair it and choose the folder in Settings → JARVIS.",
    jarvisStarted: "Task started. I will ask you before any file is sent and before anything goes to Telegram.",
  },
  ru: {
    needPermission: "Это действие не разрешено. Включите его в настройках EZO.",
    opened: (name: string) => `${name} открыт.`,
    volume: { up: "Громкость увеличена.", down: "Громкость уменьшена.", mute: "Звук выключен/включён." } as Record<VolumeChange, string>,
    typed: "Текст введён в активное окно.",
    addFolder: "Сначала добавьте в настройках папку, в которой EZO может искать.",
    notFound: (q: string) => `Файл «${q}» в разрешённых папках не найден.`,
    found: (n: number, list: string) => `Найдено файлов: ${n}\n${list}\nСкажите «открой первый», чтобы открыть.`,
    searchFirst: "Сначала найдите файл.",
    outside: "Этот файл находится вне разрешённых папок.",
    fileOpened: (name: string) => `Открыт «${name}».`,
    screenConfirm: "EZO сделает снимок экрана и отправит его на сервер EZO для анализа. Продолжить?",
    cancelled: "Отменено. Снимок экрана не сделан.",
    jarvisNotPaired: "Этот компьютер не подключён к JARVIS. Подключите его и выберите папку в Настройки → JARVIS.",
    jarvisStarted: "Задача начата. Я спрошу вас перед отправкой файлов и перед отправкой в Telegram.",
  },
};

export function replies(lang: Lang) {
  return { ...TEXT[lang], app: (id: AppId) => APP_NAMES[lang][id] };
}
