"use client";

import { Button, Card, cn, Spinner } from "@ezo/ui";
import { Check, Link2, Monitor, Play, RotateCcw, Send, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import {
  jarvisCall,
  JarvisCallError,
  type JarvisDevice,
  type JarvisRecipient,
  type JarvisStep,
  type JarvisTask,
} from "@/lib/jarvis-api";

/**
 * JARVIS owner console: pair devices with the code shown on the device, link Telegram
 * recipients (they press Start in EZO's bot), start document tasks and approve the
 * EXACT external action shown. Every status comes from the API; nothing is assumed.
 */
const INPUT =
  "w-full rounded-lg border border-line bg-surface-raised px-3 py-2 text-sm text-ink outline-none focus:border-accent focus:ring-1 focus:ring-accent";

const REFERENCE =
  "Downloads ichidagi eng oxirgi faylni och, PDF'ga aylantir, foiz ko'rsatkichlarini undan oldingi faylga o'xshatib tayyorla va Telegram'da Baxtiyorga yubor.";

const STEP_LABELS: Record<string, string> = {
  "files.latest_documents": "Qurilmadan fayllar",
  "document.extract": "Matnni o‘qish",
  "compute.percentages": "Foizlarni hisoblash",
  "document.convert_pdf": "PDF’ga aylantirish",
  "document.report_pdf": "Foizlar hisoboti",
  "telegram.send": "Telegram’ga yuborish",
};

const STATE_LABELS: Record<string, string> = {
  queued: "navbatda",
  pending: "kutmoqda",
  running: "bajarilmoqda",
  awaiting_device: "qurilma javobini kutmoqda",
  awaiting_authorization: "sizning tasdig‘ingizni kutmoqda",
  completed: "bajarildi",
  failed: "xato",
  cancelled: "bekor qilindi",
};

function message(error: unknown): string {
  if (error instanceof JarvisCallError) return error.message;
  return "Server bilan aloqa bo‘lmadi.";
}

export function JarvisConsole() {
  const [devices, setDevices] = useState<JarvisDevice[] | null>(null);
  const [recipients, setRecipients] = useState<JarvisRecipient[]>([]);
  const [tasks, setTasks] = useState<JarvisTask[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((n) => n + 1), []);

  useEffect(() => {
    let alive = true;
    Promise.all([
      jarvisCall<JarvisDevice[]>("/api/jarvis/devices"),
      jarvisCall<JarvisRecipient[]>("/api/jarvis/telegram/recipients"),
      jarvisCall<JarvisTask[]>("/api/jarvis/tasks"),
    ])
      .then(([d, r, t]) => {
        if (!alive) return;
        setDevices(d);
        setRecipients(r);
        setTasks(t);
        setError(null);
      })
      .catch((err: unknown) => alive && setError(message(err)));
    return () => {
      alive = false;
    };
  }, [tick]);

  useEffect(() => {
    // Running tasks change on the server (device answers, worker steps): refresh gently.
    const timer = setInterval(reload, 5000);
    return () => clearInterval(timer);
  }, [reload]);

  const act = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      reload();
    } catch (err) {
      setError(message(err));
    }
  };

  return (
    <div className="space-y-6" data-testid="jarvis-console">
      {error && (
        <p role="alert" className="rounded-lg border border-red-500/40 bg-red-500/5 px-3 py-2 text-sm text-red-600">
          {error}
        </p>
      )}
      <Devices devices={devices} act={act} />
      <Recipients recipients={recipients} act={act} />
      <NewTask act={act} />
      <Tasks tasks={tasks} act={act} />
    </div>
  );
}

type Act = (fn: () => Promise<unknown>) => Promise<void>;

function Devices({ devices, act }: { devices: JarvisDevice[] | null; act: Act }) {
  const [codes, setCodes] = useState<Record<string, string>>({});
  return (
    <Card className="p-5" data-testid="jarvis-devices">
      <h2 className="mb-1 flex items-center gap-2 text-sm font-semibold text-ink">
        <Monitor className="h-4 w-4" aria-hidden /> Ulangan qurilmalar
      </h2>
      <p className="mb-3 text-xs text-ink-muted">
        EZO desktop ilovasida: Sozlamalar → JARVIS → “Bu kompyuterni ulash”. Qurilmada ko‘rsatilgan 6 xonali kodni shu yerga kiriting.
      </p>
      {devices === null ? (
        <Spinner />
      ) : devices.length === 0 ? (
        <p className="text-sm text-ink-muted">Hali qurilma yo‘q.</p>
      ) : (
        <ul className="space-y-2">
          {devices.map((d) => (
            <li key={d.id} className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-medium text-ink">{d.name}</span>
              <span className={cn("rounded px-1.5 text-xs", d.status === "paired" ? "bg-emerald-500/10 text-emerald-600" : "bg-amber-500/10 text-amber-600")}>
                {d.status === "paired" ? "ulangan" : d.status === "pending" ? "tasdiq kutmoqda" : "bekor qilingan"}
              </span>
              {d.status === "pending" && (
                <>
                  <input
                    aria-label="Qurilmadagi kod"
                    inputMode="numeric"
                    maxLength={6}
                    className={cn(INPUT, "w-28")}
                    value={codes[d.id] ?? ""}
                    onChange={(e) => setCodes({ ...codes, [d.id]: e.target.value.replace(/\D/g, "") })}
                  />
                  <Button size="sm" onClick={() => void act(() => jarvisCall(`/api/jarvis/devices/${d.id}/confirm`, { method: "POST", body: { code: codes[d.id] ?? "" } }))}>
                    Tasdiqlash
                  </Button>
                </>
              )}
              {d.status !== "revoked" && (
                <Button size="sm" variant="secondary" onClick={() => void act(() => jarvisCall(`/api/jarvis/devices/${d.id}`, { method: "DELETE" }))}>
                  Bekor qilish
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Recipients({ recipients, act }: { recipients: JarvisRecipient[]; act: Act }) {
  const [label, setLabel] = useState("");
  const [pending, setPending] = useState<Record<string, { code: string; link: string }>>({});
  return (
    <Card className="p-5" data-testid="jarvis-recipients">
      <h2 className="mb-1 flex items-center gap-2 text-sm font-semibold text-ink">
        <Link2 className="h-4 w-4" aria-hidden /> Telegram qabul qiluvchilar
      </h2>
      <p className="mb-3 text-xs text-ink-muted">
        Telegram botlari faqat ularni “Start” qilgan odamga yoza oladi. Havolani odamga yuboring; u Start bosgach, “Tekshirish”ni bosing.
      </p>
      <div className="mb-3 flex gap-2">
        <input aria-label="Ism" placeholder="Masalan: Baxtiyor" className={INPUT} value={label} onChange={(e) => setLabel(e.target.value)} />
        <Button
          size="sm"
          disabled={label.trim().length < 2}
          onClick={() =>
            void act(async () => {
              const created = await jarvisCall<{ recipient: JarvisRecipient; code: string; link: string }>("/api/jarvis/telegram/recipients", {
                method: "POST",
                body: { label: label.trim() },
              });
              setPending({ ...pending, [created.recipient.id]: { code: created.code, link: created.link } });
              setLabel("");
            })
          }
        >
          Qo‘shish
        </Button>
      </div>
      <ul className="space-y-2">
        {recipients.map((r) => (
          <li key={r.id} className="text-sm">
            <span className="font-medium text-ink">{r.label}</span>{" "}
            {r.status === "verified" ? (
              <span className="text-xs text-emerald-600">✓ bog‘langan{r.telegram_name ? ` (${r.telegram_name})` : ""}</span>
            ) : pending[r.id] ? (
              <span className="inline-flex flex-wrap items-center gap-2">
                <a className="text-xs text-accent underline" href={pending[r.id]!.link} target="_blank" rel="noreferrer">
                  {pending[r.id]!.link}
                </a>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => void act(() => jarvisCall(`/api/jarvis/telegram/recipients/${r.id}/verify`, { method: "POST", body: { code: pending[r.id]!.code } }))}
                >
                  Tekshirish
                </Button>
              </span>
            ) : (
              <span className="text-xs text-amber-600">bog‘lanmagan — qayta qo‘shing</span>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function NewTask({ act }: { act: Act }) {
  const [text, setText] = useState(REFERENCE);
  return (
    <Card className="p-5" data-testid="jarvis-new-task">
      <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold text-ink">
        <Play className="h-4 w-4" aria-hidden /> Yangi vazifa
      </h2>
      <textarea aria-label="Vazifa matni" rows={3} className={INPUT} value={text} onChange={(e) => setText(e.target.value)} />
      <div className="mt-2 flex justify-end">
        <Button
          size="sm"
          disabled={text.trim().length < 5}
          onClick={() =>
            void act(() =>
              jarvisCall("/api/jarvis/tasks", { method: "POST", body: { text: text.trim(), idempotency_key: crypto.randomUUID() } }),
            )
          }
        >
          Boshlash
        </Button>
      </div>
    </Card>
  );
}

function Approval({ task, step, act }: { task: JarvisTask; step: JarvisStep; act: Act }) {
  const output = step.output as { recipient?: string; telegram_name?: string; documents?: { filename: string; sha256: string }[] };
  const decide = (approve: boolean) =>
    act(() =>
      jarvisCall(`/api/jarvis/tasks/${task.id}/steps/${step.id}/decision`, {
        method: "POST",
        body: { scope_sha256: step.scope_sha256, approve },
      }),
    );
  return (
    <div className="mt-2 rounded-lg border border-amber-500/40 bg-amber-500/5 p-3 text-sm" data-testid="jarvis-approval">
      <p className="font-medium text-ink">
        <Send className="mr-1 inline h-3.5 w-3.5" aria-hidden />
        Telegram’da {output.recipient}
        {output.telegram_name ? ` (${output.telegram_name})` : ""}ga yuborilsinmi?
      </p>
      <ul className="my-1 list-disc pl-5 text-xs text-ink-muted">
        {(output.documents ?? []).map((d) => (
          <li key={d.sha256}>
            {d.filename} <span className="font-mono">{d.sha256.slice(0, 12)}…</span>
          </li>
        ))}
      </ul>
      <div className="flex gap-2">
        <Button size="sm" onClick={() => void decide(true)}>
          <Check className="mr-1 h-3.5 w-3.5" /> Ruxsat beraman
        </Button>
        <Button size="sm" variant="secondary" onClick={() => void decide(false)}>
          <X className="mr-1 h-3.5 w-3.5" /> Rad etish
        </Button>
      </div>
    </div>
  );
}

function Tasks({ tasks, act }: { tasks: JarvisTask[]; act: Act }) {
  if (tasks.length === 0) return null;
  return (
    <Card className="p-5" data-testid="jarvis-tasks">
      <h2 className="mb-3 text-sm font-semibold text-ink">Vazifalar</h2>
      <ul className="space-y-4">
        {tasks.map((task) => (
          <li key={task.id} className="border-b border-line pb-3 last:border-0">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm text-ink">{task.request_text}</p>
              <span className="text-xs font-medium text-ink-muted">{STATE_LABELS[task.state] ?? task.state}</span>
            </div>
            <ol className="mt-2 space-y-1 text-xs">
              {task.steps.map((step) => (
                <li key={step.id}>
                  <span className={cn(step.state === "completed" ? "text-emerald-600" : step.state === "failed" ? "text-red-600" : "text-ink-muted")}>
                    {step.position}. {STEP_LABELS[step.action] ?? step.action} — {STATE_LABELS[step.state] ?? step.state}
                    {step.error_message ? `: ${step.error_message}` : ""}
                  </span>
                  {step.state === "awaiting_authorization" && step.scope_sha256 && <Approval task={task} step={step} act={act} />}
                </li>
              ))}
            </ol>
            {task.report && <pre className="mt-2 whitespace-pre-wrap text-xs text-ink">{task.report}</pre>}
            <div className="mt-2 flex gap-2">
              {["queued", "running", "awaiting_authorization"].includes(task.state) && (
                <Button size="sm" variant="secondary" onClick={() => void act(() => jarvisCall(`/api/jarvis/tasks/${task.id}/cancel`, { method: "POST" }))}>
                  Bekor qilish
                </Button>
              )}
              {task.state === "failed" && (
                <Button size="sm" variant="secondary" onClick={() => void act(() => jarvisCall(`/api/jarvis/tasks/${task.id}/retry`, { method: "POST" }))}>
                  <RotateCcw className="mr-1 h-3.5 w-3.5" /> Qayta urinish
                </Button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}
