/** Texts of the jarvisConsole surface. Uzbek is the reference; en and ru must have every key. */
const uz = {
  /** Example command shown in the new-task box; "Baxtiyor" is a sample name, not a real contact. */
  sampleCommand:
    "Downloads ichidagi eng oxirgi faylni och, PDF'ga aylantir, foiz ko'rsatkichlarini undan oldingi faylga o'xshatib tayyorla va Telegram'da Baxtiyorga yubor.",
  serverUnreachable: "Server bilan aloqa bo‘lmadi.",
  steps: {
    filesLatestDocuments: "Qurilmadan fayllar",
    documentExtract: "Matnni o‘qish",
    computePercentages: "Foizlarni hisoblash",
    documentConvertPdf: "PDF’ga aylantirish",
    documentReportPdf: "Foizlar hisoboti",
    telegramSend: "Telegram’ga yuborish",
  },
  states: {
    queued: "navbatda",
    pending: "kutmoqda",
    running: "bajarilmoqda",
    awaitingDevice: "qurilma javobini kutmoqda",
    awaitingAuthorization: "sizning tasdig‘ingizni kutmoqda",
    completed: "bajarildi",
    failed: "xato",
    cancelled: "bekor qilindi",
  },
  devices: {
    title: "Ulangan qurilmalar",
    hint: "EZO desktop ilovasida: Sozlamalar → JARVIS → “Bu kompyuterni ulash”. Qurilmada ko‘rsatilgan 6 xonali kodni shu yerga kiriting.",
    empty: "Hali qurilma yo‘q.",
    statusPaired: "ulangan",
    statusPending: "tasdiq kutmoqda",
    statusRevoked: "bekor qilingan",
    codeLabel: "Qurilmadagi kod",
    confirm: "Tasdiqlash",
    revoke: "Bekor qilish",
  },
  recipients: {
    title: "Telegram qabul qiluvchilar",
    hint: "Telegram botlari faqat ularni “Start” qilgan odamga yoza oladi. Havolani odamga yuboring; u Start bosgach, “Tekshirish”ni bosing.",
    nameLabel: "Ism",
    /** Example name only. */
    namePlaceholder: "Masalan: Baxtiyor",
    add: "Qo‘shish",
    linked: "✓ bog‘langan",
    verify: "Tekshirish",
    notLinked: "bog‘lanmagan — qayta qo‘shing",
  },
  newTask: {
    title: "Yangi vazifa",
    textLabel: "Vazifa matni",
    start: "Boshlash",
  },
  approval: {
    /** {recipient} is the recipient label, optionally followed by the Telegram name in parentheses. */
    question: "Telegram’da {recipient}ga yuborilsinmi?",
    approve: "Ruxsat beraman",
    reject: "Rad etish",
  },
  tasks: {
    title: "Vazifalar",
    cancel: "Bekor qilish",
    retry: "Qayta urinish",
  },
};
export type Section = typeof uz;

const en: Section = {
  sampleCommand:
    "Open the newest file in Downloads, convert it to PDF, prepare the percentage figures the same way as the previous file, and send it on Telegram to Bakhtiyor (example name).",
  serverUnreachable: "Could not reach the server.",
  steps: {
    filesLatestDocuments: "Files from the device",
    documentExtract: "Read the text",
    computePercentages: "Calculate percentages",
    documentConvertPdf: "Convert to PDF",
    documentReportPdf: "Percentage report",
    telegramSend: "Send on Telegram",
  },
  states: {
    queued: "queued",
    pending: "pending",
    running: "running",
    awaitingDevice: "waiting for the device to respond",
    awaitingAuthorization: "waiting for your approval",
    completed: "completed",
    failed: "failed",
    cancelled: "cancelled",
  },
  devices: {
    title: "Paired devices",
    hint: "In the EZO desktop app: Settings → JARVIS → “Pair this computer”. Enter the 6-digit code shown on the device here.",
    empty: "No devices yet.",
    statusPaired: "paired",
    statusPending: "awaiting confirmation",
    statusRevoked: "revoked",
    codeLabel: "Code on the device",
    confirm: "Confirm",
    revoke: "Revoke",
  },
  recipients: {
    title: "Telegram recipients",
    hint: "Telegram bots can only write to people who have pressed “Start”. Send the link to the person; once they press Start, press “Check”.",
    nameLabel: "Name",
    namePlaceholder: "For example: Bakhtiyor",
    add: "Add",
    linked: "✓ linked",
    verify: "Check",
    notLinked: "not linked — add again",
  },
  newTask: {
    title: "New task",
    textLabel: "Task text",
    start: "Start",
  },
  approval: {
    question: "Send to {recipient} on Telegram?",
    approve: "Allow",
    reject: "Decline",
  },
  tasks: {
    title: "Tasks",
    cancel: "Cancel",
    retry: "Retry",
  },
};

const ru: Section = {
  sampleCommand:
    "Открой самый новый файл в Downloads, преобразуй его в PDF, подготовь процентные показатели по образцу предыдущего файла и отправь в Telegram Бахтиёру (имя для примера).",
  serverUnreachable: "Нет связи с сервером.",
  steps: {
    filesLatestDocuments: "Файлы с устройства",
    documentExtract: "Чтение текста",
    computePercentages: "Расчёт процентов",
    documentConvertPdf: "Преобразование в PDF",
    documentReportPdf: "Отчёт по процентам",
    telegramSend: "Отправка в Telegram",
  },
  states: {
    queued: "в очереди",
    pending: "ожидает",
    running: "выполняется",
    awaitingDevice: "ожидает ответа устройства",
    awaitingAuthorization: "ожидает вашего подтверждения",
    completed: "выполнено",
    failed: "ошибка",
    cancelled: "отменено",
  },
  devices: {
    title: "Подключённые устройства",
    hint: "В приложении EZO для компьютера: Настройки → JARVIS → «Подключить этот компьютер». Введите здесь 6-значный код, показанный на устройстве.",
    empty: "Устройств пока нет.",
    statusPaired: "подключено",
    statusPending: "ожидает подтверждения",
    statusRevoked: "отключено",
    codeLabel: "Код на устройстве",
    confirm: "Подтвердить",
    revoke: "Отключить",
  },
  recipients: {
    title: "Получатели в Telegram",
    hint: "Боты Telegram могут писать только тем, кто нажал «Start». Отправьте ссылку человеку; когда он нажмёт Start, нажмите «Проверить».",
    nameLabel: "Имя",
    namePlaceholder: "Например: Бахтиёр",
    add: "Добавить",
    linked: "✓ привязан",
    verify: "Проверить",
    notLinked: "не привязан — добавьте заново",
  },
  newTask: {
    title: "Новая задача",
    textLabel: "Текст задачи",
    start: "Запустить",
  },
  approval: {
    question: "Отправить {recipient} в Telegram?",
    approve: "Разрешаю",
    reject: "Отклонить",
  },
  tasks: {
    title: "Задачи",
    cancel: "Отменить",
    retry: "Повторить",
  },
};

export const jarvisConsole = { uz, en, ru };
