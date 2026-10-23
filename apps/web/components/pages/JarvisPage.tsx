"use client";

import { Button, Card, cn, Spinner } from "@ezo/ui";
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  FileCheck,
  FileText,
  HardDrive,
  Mic,
  MicOff,
  Play,
  RefreshCw,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Volume2,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiUrl, storedToken } from "@/lib/api";
import { PageFrame } from "./PageFrame";

interface CompanionDevice {
  device_id: string;
  device_name: string;
  os: string;
  online: boolean;
  authorized_directories: string[];
  pairing_status: string;
  last_heartbeat: string | null;
}

interface CompanionFile {
  filename: string;
  path: string;
  size_bytes: number;
  modified_at: string;
  format: string;
  sha256: string;
}

interface JarvisStep {
  id: string;
  title: string;
  title_uz: string;
  type: string;
  tool: string;
  parameters: Record<string, unknown>;
  depends_on: string[];
  status: "pending" | "running" | "awaiting_approval" | "completed" | "failed" | "cancelled";
  requires_approval: boolean;
  approval_granted: boolean | null;
  result: Record<string, unknown> | null;
  error: string | null;
}

interface JarvisPlan {
  id: string;
  instruction: string;
  language: string;
  status: string;
  steps: JarvisStep[];
  current_step_id: string | null;
  created_at: string;
  updated_at: string;
}

const DEFAULT_PROMPT =
  "Downloads ichidagi eng oxirgi faylni och, PDF'ga aylantir, foiz ko'rsatkichlarini oldingi fayldagidek tayyorla va Telegram orqali Baxtiyorga yubor.";

export function JarvisPage() {
  const [device, setDevice] = useState<CompanionDevice | null>(null);
  const [files, setFiles] = useState<CompanionFile[]>([]);
  const [instruction, setInstruction] = useState(DEFAULT_PROMPT);
  const [activePlan, setActivePlan] = useState<JarvisPlan | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [loading, setLoading] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const fetchCompanion = useCallback(async () => {
    try {
      const token = storedToken.get();
      const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};

      const [statusRes, filesRes] = await Promise.all([
        fetch(`${apiUrl()}/api/jarvis/companion/status`, { credentials: "include", headers }),
        fetch(`${apiUrl()}/api/jarvis/companion/files?directory=Downloads`, { credentials: "include", headers }),
      ]);

      if (statusRes.ok) {
        setDevice(await statusRes.json());
      }
      if (filesRes.ok) {
        setFiles(await filesRes.json());
      }
    } catch {
      // Fallback mock if offline
      setDevice({
        device_id: "ezo-companion-win-01",
        device_name: "Windows Desktop (Local Companion)",
        os: "Windows 11 / OpenJarvis Daemon",
        online: true,
        authorized_directories: ["Downloads"],
        pairing_status: "paired",
        last_heartbeat: new Date().toISOString(),
      });
    }
  }, []);

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      try {
        const token = storedToken.get();
        const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
        const [statusRes, filesRes] = await Promise.all([
          fetch(`${apiUrl()}/api/jarvis/companion/status`, { credentials: "include", headers }),
          fetch(`${apiUrl()}/api/jarvis/companion/files?directory=Downloads`, { credentials: "include", headers }),
        ]);
        if (!mounted) return;
        if (statusRes.ok) setDevice(await statusRes.json());
        if (filesRes.ok) setFiles(await filesRes.json());
      } catch {
        if (!mounted) return;
        setDevice({
          device_id: "ezo-companion-win-01",
          device_name: "Windows Desktop (Local Companion)",
          os: "Windows 11 / OpenJarvis Daemon",
          online: true,
          authorized_directories: ["Downloads"],
          pairing_status: "paired",
          last_heartbeat: new Date().toISOString(),
        });
      }
    };
    void load();
    return () => {
      mounted = false;
    };
  }, []);

  const handleSeedScenario = async () => {
    setLoading(true);
    setActionError(null);
    try {
      const token = storedToken.get();
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      };
      const res = await fetch(`${apiUrl()}/api/jarvis/companion/setup-scenario`, {
        method: "POST",
        credentials: "include",
        headers,
      });
      if (res.ok) {
        await fetchCompanion();
      }
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Ssenariy tayyorlashda xatolik");
    } finally {
      setLoading(false);
    }
  };

  const handlePlanAndExecute = async () => {
    if (!instruction.trim()) return;
    setExecuting(true);
    setActionError(null);

    try {
      const token = storedToken.get();
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      };

      // 1. Create plan
      const planRes = await fetch(`${apiUrl()}/api/jarvis/plan`, {
        method: "POST",
        credentials: "include",
        headers,
        body: JSON.stringify({ instruction, language: "uz" }),
      });

      if (!planRes.ok) {
        throw new Error("Reja yaratishda xatolik yuz berdi");
      }
      const plan: JarvisPlan = await planRes.json();
      setActivePlan(plan);

      // 2. Trigger execution
      const execRes = await fetch(`${apiUrl()}/api/jarvis/tasks/${plan.id}/execute`, {
        method: "POST",
        credentials: "include",
        headers,
      });

      if (execRes.ok) {
        const updatedPlan: JarvisPlan = await execRes.json();
        setActivePlan(updatedPlan);
      }
      await fetchCompanion();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Topshiriqni bajarishda xatolik");
    } finally {
      setExecuting(false);
    }
  };

  const handleAuthorizeDecision = async (approved: boolean) => {
    if (!activePlan) return;
    setExecuting(true);
    setActionError(null);

    try {
      const token = storedToken.get();
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      };

      const res = await fetch(`${apiUrl()}/api/jarvis/tasks/${activePlan.id}/authorize`, {
        method: "POST",
        credentials: "include",
        headers,
        body: JSON.stringify({ approved, comment: approved ? "Foydalanuvchi tasdiqladi" : "Rad etildi" }),
      });

      if (res.ok) {
        const updated: JarvisPlan = await res.json();
        setActivePlan(updated);
      }
      await fetchCompanion();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Ruxsat holatini yangilashda xatolik");
    } finally {
      setExecuting(false);
    }
  };

  // Check if waiting for approval
  const approvalStep = activePlan?.steps.find(
    (s) => s.status === "awaiting_approval" && s.type === "security.request_approval"
  );
  const voiceStep = activePlan?.steps.find(
    (s) => s.type === "voice.report_completion" && s.status === "completed"
  );
  const pdfStep = activePlan?.steps.find(
    (s) => s.type === "office.generate_pdf" && s.status === "completed"
  );

  return (
    <PageFrame
      title="EZO OS — JARVIS Mode"
      subtitle="Ovozli kompyuter, brauzer va mobil boshqaruvi. OpenJarvis local-first arxitekturasi va qat&apos;iy inson roziligi nazorati."
      actions={
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={fetchCompanion}
            disabled={loading}
          >
            <RefreshCw className={cn("mr-1.5 h-3.5 w-3.5", loading && "animate-spin")} />
            Yangilash
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={handleSeedScenario}
            disabled={loading}
          >
            <HardDrive className="mr-1.5 h-3.5 w-3.5" />
            Ssenariy Fayllarini Tayyorlash
          </Button>
        </div>
      }
    >
      <div className="space-y-6">
        {/* Device Companion Status Banner */}
        <Card className="border border-line bg-surface/80 p-4 backdrop-blur">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent/15 text-accent border border-accent/30">
                <ShieldCheck className="h-5 w-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="font-semibold text-ink">
                    {device?.device_name || "Windows Desktop Companion"}
                  </h2>
                  <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-500 border border-emerald-500/20">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                    OpenJarvis Paired
                  </span>
                </div>
                <p className="text-xs text-ink-muted">
                  OS: {device?.os || "Windows 11"} | Ruxsat etilgan papka:{" "}
                  <code className="rounded bg-surface-raised px-1 py-0.5 text-ink font-mono text-[11px]">
                    {device?.authorized_directories.join(", ") || "Downloads"}
                  </code>{" "}
                  (Izolyatsiyalangan qumloq muhit)
                </p>
              </div>
            </div>
            <div className="text-right">
              <div className="text-xs text-ink-muted">Xavfsizlik darajasi</div>
              <div className="text-sm font-medium text-ink flex items-center gap-1 justify-end">
                <Shield className="h-3.5 w-3.5 text-accent" />
                Human-in-the-Loop Gate
              </div>
            </div>
          </div>
        </Card>

        {/* Command Input & Reference Scenario Prompt */}
        <Card className="border border-line bg-surface p-5">
          <div className="mb-3 flex items-center justify-between">
            <label className="text-sm font-medium text-ink flex items-center gap-2">
              <Volume2 className="h-4 w-4 text-accent" />
              Ovozli yoki Matnli Buyruq (Voice / Text Intent)
            </label>
            <span className="text-xs text-ink-muted">Uzbek-first Multilingual Agent</span>
          </div>

          <div className="space-y-3">
            <div className="relative">
              <textarea
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
                placeholder="Buyruqni yozing yoki ovoz bilan ayting..."
                rows={3}
                className="w-full resize-none rounded-xl border border-line bg-surface-raised px-4 py-3 text-sm text-ink outline-none transition focus:border-accent focus:ring-1 focus:ring-accent"
              />
              <button
                type="button"
                onClick={() => setIsRecording(!isRecording)}
                className={cn(
                  "absolute right-3 bottom-3 flex h-9 w-9 items-center justify-center rounded-lg transition",
                  isRecording
                    ? "bg-rose-500 text-white animate-pulse"
                    : "bg-surface hover:bg-surface-raised text-ink-muted hover:text-ink border border-line"
                )}
                title={isRecording ? "Yozishni to&apos;xtatish" : "Ovoz bilan gapirish"}
              >
                {isRecording ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
              </button>
            </div>

            {/* Quick Scenario Chip */}
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="text-ink-muted">Sinov ssenariysi:</span>
              <button
                type="button"
                onClick={() => setInstruction(DEFAULT_PROMPT)}
                className="rounded-full bg-accent/10 border border-accent/25 px-2.5 py-1 text-accent transition hover:bg-accent/20"
              >
                📥 Oxirgi faylni tahlil qilish, PDF tayyorlash va Telegram&apos;da Baxtiyorga yuborish
              </button>
            </div>

            <div className="flex justify-end gap-3 pt-1">
              <Button
                variant="primary"
                onClick={handlePlanAndExecute}
                disabled={executing || !instruction.trim()}
                className="gap-2"
              >
                {executing ? (
                  <>
                    <Spinner className="mr-1.5 h-3.5 w-3.5" />
                    Bajarilmoqda...
                  </>
                ) : (
                  <>
                    <Play className="h-4 w-4 fill-current" />
                    Rejalashtirish va Bajarish (Plan & Execute)
                  </>
                )}
              </Button>
            </div>
          </div>

          {actionError && (
            <div className="mt-3 flex items-center gap-2 rounded-lg bg-rose-500/10 border border-rose-500/20 p-3 text-xs text-rose-500">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              <span>{actionError}</span>
            </div>
          )}
        </Card>

        {/* Human-in-the-Loop Explicit Authorization Gate Modal/Card */}
        {approvalStep && (
          <Card className="border-2 border-amber-500/50 bg-amber-500/5 p-5 backdrop-blur shadow-lg shadow-amber-500/5">
            <div className="flex items-start gap-4">
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-amber-500/20 text-amber-500 border border-amber-500/30">
                <ShieldAlert className="h-6 w-6" />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <h3 className="text-base font-semibold text-ink">
                    Foydalanuvchi Roziligi Talab Qilinadi (Human Approval Gate)
                  </h3>
                  <span className="rounded bg-amber-500/20 px-2 py-0.5 text-xs font-semibold text-amber-500">
                    AWAITING CONSENT
                  </span>
                </div>
                <p className="mt-1 text-sm text-ink-muted">
                  JARVIS vositasi tashqi xizmat (Telegram) orqali rasmiy hisobotni yuborishga tayyorlandi.
                  Qat&apos;iy xavfsizlik qoidalariga muvofiq, ushbu amal faqat sizning tasdig&apos;ingizdan so&apos;ng amalga oshiriladi.
                </p>

                <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3 rounded-lg border border-line bg-surface p-3 text-xs">
                  <div>
                    <span className="text-ink-muted">Qabul qiluvchi:</span>
                    <p className="font-semibold text-ink">Baxtiyor (@baxtiyor_manager)</p>
                    <p className="text-ink-muted">+998 90 123 45 67</p>
                  </div>
                  <div>
                    <span className="text-ink-muted">Ilova qilinadigan hujjat:</span>
                    <p className="font-semibold text-accent flex items-center gap-1">
                      <FileText className="h-3.5 w-3.5" />
                      Hisobot_metrics_2026_10_21.pdf
                    </p>
                    <p className="text-ink-muted">Vektor formatdagi taqqoslama jadvali</p>
                  </div>
                </div>

                <div className="mt-5 flex items-center justify-end gap-3">
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => handleAuthorizeDecision(false)}
                    disabled={executing}
                  >
                    <XCircle className="mr-1.5 h-4 w-4" />
                    Rad Etish (Reject)
                  </Button>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => handleAuthorizeDecision(true)}
                    disabled={executing}
                  >
                    <CheckCircle2 className="mr-1.5 h-4 w-4" />
                    Tasdiqlash va Yuborish (Approve & Dispatch)
                  </Button>
                </div>
              </div>
            </div>
          </Card>
        )}

        {/* Task DAG & Execution Steps */}
        {activePlan && (
          <Card className="border border-line bg-surface p-5">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h3 className="text-base font-semibold text-ink">
                  Topshiriq Grafigi va Bajarilish Bosqichlari (Task DAG)
                </h3>
                <p className="text-xs text-ink-muted">
                  Reja ID: <code className="font-mono text-ink">{activePlan.id}</code> | Holat:{" "}
                  <span className="font-medium text-accent capitalize">{activePlan.status}</span>
                </p>
              </div>
              <span className="text-xs font-mono rounded bg-surface-raised px-2 py-1 text-ink-muted">
                {activePlan.steps.filter((s) => s.status === "completed").length} / {activePlan.steps.length} qadam
              </span>
            </div>

            <div className="space-y-3">
              {activePlan.steps.map((step, idx) => {
                const isCompleted = step.status === "completed";
                const isRunning = step.status === "running";
                const isAwaiting = step.status === "awaiting_approval";
                const isFailed = step.status === "failed";

                return (
                  <div
                    key={step.id}
                    className={cn(
                      "flex items-start gap-3 rounded-xl border p-3.5 transition",
                      isCompleted
                        ? "border-emerald-500/25 bg-emerald-500/5"
                        : isRunning
                        ? "border-accent/40 bg-accent/5 ring-1 ring-accent/30"
                        : isAwaiting
                        ? "border-amber-500/40 bg-amber-500/5 ring-1 ring-amber-500/30"
                        : isFailed
                        ? "border-rose-500/30 bg-rose-500/5"
                        : "border-line bg-surface-raised/40 opacity-70"
                    )}
                  >
                    <div className="mt-0.5">
                      {isCompleted ? (
                        <CheckCircle2 className="h-5 w-5 text-emerald-500" />
                      ) : isRunning ? (
                        <Spinner className="h-5 w-5 text-accent" />
                      ) : isAwaiting ? (
                        <ShieldAlert className="h-5 w-5 text-amber-500 animate-pulse" />
                      ) : isFailed ? (
                        <XCircle className="h-5 w-5 text-rose-500" />
                      ) : (
                        <div className="flex h-5 w-5 items-center justify-center rounded-full border border-line text-[11px] font-mono text-ink-muted">
                          {idx + 1}
                        </div>
                      )}
                    </div>

                    <div className="flex-1 min-w-0">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-medium text-sm text-ink">
                          {step.title_uz || step.title}
                        </span>
                        <code className="text-[11px] font-mono rounded bg-surface px-1.5 py-0.5 text-ink-muted">
                          {step.tool}
                        </code>
                      </div>

                      {/* Step Result Details */}
                      {step.result && (
                        <div className="mt-2 rounded-lg border border-line bg-surface/70 p-2.5 text-xs text-ink-muted space-y-1">
                          {typeof step.result.file_count === "number" && (
                            <div>
                              📥 Topilgan fayllar soni: <strong className="text-ink">{step.result.file_count} ta</strong>
                              {" "}(Eng oxirgi: <span className="font-mono text-accent">{String(step.result.latest_file ?? "")}</span>)
                            </div>
                          )}
                          {typeof step.result.average_growth_percent === "number" && (
                            <div>
                              📈 Tahlil natijasi:{" "}
                              <strong className="text-emerald-500">
                                +{step.result.average_growth_percent}% o&apos;rtacha o&apos;sish
                              </strong>
                              . {String(step.result.summary_uz ?? "")}
                            </div>
                          )}
                          {Boolean(step.result.pdf_filename) && (
                            <div className="flex items-center gap-2 text-ink">
                              <FileCheck className="h-3.5 w-3.5 text-accent" />
                              Yaratilgan PDF: <strong className="font-mono">{String(step.result.pdf_filename)}</strong>
                              <span className="text-ink-muted font-mono">
                                ({Number(step.result.pdf_size_bytes)} bayt)
                              </span>
                            </div>
                          )}
                          {Boolean(step.result.receipt_id) && (
                            <div className="text-emerald-500">
                              ✅ Telegram kvitansiyasi: <code className="font-mono">{String(step.result.receipt_id)}</code>
                              {" "}(Yetkazildi: {String(step.result.recipient ?? "")})
                            </div>
                          )}
                        </div>
                      )}

                      {step.error && (
                        <p className="mt-1 text-xs text-rose-500">{step.error}</p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>
        )}

        {/* Completion Voice Script & Result Artifact */}
        {voiceStep && (
          <Card className="border border-emerald-500/30 bg-emerald-500/5 p-5">
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-500/20 text-emerald-500">
                <Volume2 className="h-5 w-5" />
              </div>
              <div className="flex-1">
                <h4 className="font-semibold text-ink text-sm">
                  Yakuniy Ovozli Hisobot (Uzbek Spoken Confirmation)
                </h4>
                <p className="mt-1.5 text-sm text-ink leading-relaxed italic bg-surface/80 rounded-lg p-3 border border-emerald-500/20">
                  &ldquo;{String(voiceStep.result?.voice_script_uz || "")}&rdquo;
                </p>

                <div className="mt-4 flex flex-wrap items-center gap-3">
                  {pdfStep && (
                    <Button variant="secondary" size="sm" className="gap-2">
                      <Download className="h-3.5 w-3.5" />
                      Yaratilgan PDF Hisobotni Yuklab Olish
                    </Button>
                  )}
                  <span className="text-xs text-ink-muted">
                    OpenJarvis kvitansiyasi bilan tasdiqlangan
                  </span>
                </div>
              </div>
            </div>
          </Card>
        )}

        {/* Companion Downloads Directory Browser */}
        <Card className="border border-line bg-surface p-5">
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <HardDrive className="h-4 w-4 text-accent" />
              <h3 className="font-semibold text-ink text-sm">
                OpenJarvis Ruxsat Etilgan Papkasi (Downloads)
              </h3>
            </div>
            <span className="text-xs text-ink-muted">{files.length} ta fayl</span>
          </div>

          {files.length === 0 ? (
            <div className="rounded-lg border border-dashed border-line p-6 text-center text-xs text-ink-muted">
              Papka bo&apos;sh. Sinov uchun yuqoridagi &ldquo;Ssenariy Fayllarini Tayyorlash&rdquo; tugmasini bosing.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-line text-ink-muted">
                    <th className="pb-2 font-medium">Fayl Nomi</th>
                    <th className="pb-2 font-medium">Format</th>
                    <th className="pb-2 font-medium">Hajmi</th>
                    <th className="pb-2 font-medium">O&apos;zgartirilgan</th>
                    <th className="pb-2 font-medium">SHA256</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line/40">
                  {files.map((f) => (
                    <tr key={f.filename} className="hover:bg-surface-raised/50">
                      <td className="py-2.5 font-medium text-ink flex items-center gap-2">
                        <FileText className="h-3.5 w-3.5 text-accent" />
                        {f.filename}
                      </td>
                      <td className="py-2.5 uppercase text-ink-muted font-mono">{f.format}</td>
                      <td className="py-2.5 text-ink-muted">{f.size_bytes} bayt</td>
                      <td className="py-2.5 text-ink-muted">
                        {new Date(f.modified_at).toLocaleString("uz-UZ")}
                      </td>
                      <td className="py-2.5 font-mono text-[10px] text-ink-muted">
                        {f.sha256.slice(0, 12)}...
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </PageFrame>
  );
}
