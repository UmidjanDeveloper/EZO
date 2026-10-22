"use client";

import { Button, Card, cn, Spinner } from "@ezo/ui";
import {
  Activity,
  AlertTriangle,
  Bot,
  CheckCircle2,
  Cpu,
  Database,
  FileText,
  Lock,
  RefreshCw,
  Server,
  ShieldAlert,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiUrl, storedToken } from "@/lib/api";
import { PageFrame } from "./PageFrame";

interface GovernanceStatus {
  role: string;
  super_admin_verified: boolean;
  autonomous_code_modification: boolean;
  autonomous_pr_merge: boolean;
  autonomous_deployment: boolean;
  governance_mode: string;
  policies: Record<string, string>;
}

interface AgentInfo {
  key: string;
  names: Record<string, string>;
  description: string;
  available: boolean;
  maturity: string;
  phase: string;
}

interface SystemStatus {
  deployment_profile: string;
  disabled_capabilities: string[];
  version: string;
  environment: string;
  database: string;
  offline_mode: boolean;
  providers: Array<{
    name: string;
    display_name: string;
    configured: boolean;
    capabilities: string[];
  }>;
  routing: Record<string, unknown>;
  agents: AgentInfo[];
  debug_traces: boolean;
}

interface HealthStatus {
  status: string;
  database: string;
  version?: string;
}

interface ImprovementProposal {
  id: string;
  sha256: string;
  goal: string;
  library_id?: string;
  status: string;
  sandbox_tested: boolean;
  execution_authorized: boolean;
  required_gates?: string[];
  decision?: string;
}

export function AdminPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  // Real backend state
  const [govStatus, setGovStatus] = useState<GovernanceStatus | null>(null);
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [healthStatus, setHealthStatus] = useState<HealthStatus | null>(null);
  const [proposals, setProposals] = useState<ImprovementProposal[]>([]);
  const [actingProposalId, setActingProposalId] = useState<string | null>(null);

  const authHeaders = useCallback(() => {
    const token = storedToken.get().trim();
    return {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    setForbidden(false);

    try {
      const headers = authHeaders();

      // 1. Check governance status (Super Admin RBAC check)
      const statusRes = await fetch(`${apiUrl()}/api/admin/governance/status`, { headers });
      if (statusRes.status === 403) {
        setForbidden(true);
        setLoading(false);
        return;
      }
      if (!statusRes.ok) throw new Error(`HTTP ${statusRes.status}`);
      const statusData = (await statusRes.json()) as GovernanceStatus;
      setGovStatus(statusData);

      // 2. Load genuine system status
      const sysRes = await fetch(`${apiUrl()}/api/status`, { headers });
      if (sysRes.ok) {
        const sysData = (await sysRes.json()) as SystemStatus;
        setSystemStatus(sysData);
      }

      // 3. Load genuine health probe
      const healthRes = await fetch(`${apiUrl()}/api/health`);
      if (healthRes.ok) {
        const healthData = (await healthRes.json()) as HealthStatus;
        setHealthStatus(healthData);
      }

      // 4. Load genuine durable improvement proposals
      const propRes = await fetch(`${apiUrl()}/api/admin/governance/improvements`, { headers });
      if (propRes.ok) {
        const propData = (await propRes.json()) as ImprovementProposal[];
        setProposals(propData);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [authHeaders]);

  useEffect(() => {
    let active = true;
    const headers = authHeaders();

    Promise.allSettled([
      fetch(`${apiUrl()}/api/admin/governance/status`, { headers }),
      fetch(`${apiUrl()}/api/status`, { headers }),
      fetch(`${apiUrl()}/api/health`),
      fetch(`${apiUrl()}/api/admin/governance/improvements`, { headers }),
    ])
      .then(async ([statusRes, sysRes, healthRes, propRes]) => {
        if (!active) return;

        if (statusRes.status === "fulfilled") {
          const res = statusRes.value;
          if (res.status === 403) {
            setForbidden(true);
            setLoading(false);
            return;
          }
          if (res.ok) {
            const data = (await res.json()) as GovernanceStatus;
            if (active) setGovStatus(data);
          } else {
            if (active) setError(`HTTP ${res.status}`);
          }
        } else {
          if (active) setError(String(statusRes.reason));
        }

        if (sysRes.status === "fulfilled" && sysRes.value.ok) {
          const data = (await sysRes.value.json()) as SystemStatus;
          if (active) setSystemStatus(data);
        }

        if (healthRes.status === "fulfilled" && healthRes.value.ok) {
          const data = (await healthRes.value.json()) as HealthStatus;
          if (active) setHealthStatus(data);
        }

        if (propRes.status === "fulfilled" && propRes.value.ok) {
          const data = (await propRes.value.json()) as ImprovementProposal[];
          if (active) setProposals(data);
        }

        if (active) setLoading(false);
      })
      .catch((err: unknown) => {
        if (active) {
          setError(err instanceof Error ? err.message : String(err));
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [authHeaders]);

  async function handleDecision(proposal: ImprovementProposal, decision: "request_independent_review" | "reject") {
    setActingProposalId(proposal.id);
    try {
      const res = await fetch(`${apiUrl()}/api/admin/governance/improvements/${proposal.id}/decision`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({
          proposal_sha256: proposal.sha256,
          decision,
          confirm: true,
        }),
      });
      if (res.ok) {
        await loadData();
      } else {
        const data = (await res.json().catch(() => ({}))) as { error?: { message?: string } };
        setError(data.error?.message || `Qaror qabul qilishda xatolik: HTTP ${res.status}`);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setActingProposalId(null);
    }
  }

  return (
    <PageFrame
      title="Super Admin boshqaruvi"
      subtitle="EZO OS tizim boshqaruvi, xavfsizlik siyosatlari va arxitektura tekshiruvlari"
      actions={
        <Button
          variant="secondary"
          className="gap-2"
          onClick={() => void loadData()}
          disabled={loading}
        >
          <RefreshCw size={14} className={cn(loading && "animate-spin")} />
          Yangilash
        </Button>
      }
    >
      <div className="flex flex-col gap-6 p-4 sm:p-6 max-w-7xl mx-auto w-full">
        {/* Loading state */}
        {loading && (
          <div className="flex items-center justify-center p-12">
            <Spinner className="h-8 w-8" label="Ma'lumotlar yuklanmoqda..." />
          </div>
        )}

        {/* 403 Forbidden State */}
        {forbidden && !loading && (
          <Card className="p-8 border-danger/30 bg-danger/5 text-center flex flex-col items-center gap-4">
            <ShieldAlert size={48} className="text-danger animate-bounce" />
            <h2 className="text-xl font-bold text-danger">Kirish taqiqlangan (403 Forbidden)</h2>
            <p className="text-sm text-ink-muted max-w-md">
              Ushbu bo‘lim faqat tizim <strong>Super Admin</strong> foydalanuvchisi uchun ochiq.
            </p>
            <p className="text-sm text-ink-muted max-w-md">
              Obuna maqomi (pro, enterprise) platforma boshqaruviga ruxsat bermaydi.
            </p>
          </Card>
        )}

        {/* Error message */}
        {error && !forbidden && (
          <Card className="p-4 border-warning/30 bg-warning/5 flex items-center gap-3">
            <AlertTriangle size={20} className="text-warning flex-shrink-0" />
            <p className="text-sm text-ink">{error}</p>
          </Card>
        )}

        {/* Super Admin Dashboard Content */}
        {!loading && !forbidden && govStatus && (
          <>
            {/* Top Security Banner */}
            <Card className="p-5 border-primary/20 bg-primary/5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-xl bg-primary/10 text-primary">
                  <ShieldCheck size={24} />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold text-ink">Super Admin Autentifikatsiya Qilingan</h3>
                    <span className="px-2 py-0.5 text-xs rounded-full bg-emerald-500/10 text-emerald-600 font-medium border border-emerald-500/20">
                      Tasdiqlangan
                    </span>
                  </div>
                  <p className="text-xs text-ink-muted mt-0.5">
                    Boshqaruv rejimi: <span className="font-mono text-ink">{govStatus.governance_mode}</span> | 
                    Avtonom deploy / merge: <span className="text-emerald-600 font-medium">To‘liq bloklangan</span>
                  </p>
                </div>
              </div>
              <div className="flex flex-wrap gap-2 text-xs">
                {Object.entries(govStatus.policies).map(([key, val]) => (
                  <span
                    key={key}
                    className="px-2.5 py-1 rounded-md bg-surface-2 border border-line text-ink-muted font-mono"
                  >
                    {key}: <strong className="text-ink">{String(val)}</strong>
                  </span>
                ))}
              </div>
            </Card>

            {/* System Health & Deployment Overview */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <Card className="p-4 flex flex-col gap-2">
                <div className="flex items-center justify-between text-xs text-ink-muted">
                  <span>Ma&apos;lumotlar bazasi</span>
                  <Database size={16} className="text-primary" />
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className={cn(
                      "h-2.5 w-2.5 rounded-full",
                      healthStatus?.database === "ok" ? "bg-emerald-500" : "bg-danger"
                    )}
                  />
                  <span className="text-lg font-bold capitalize text-ink">
                    {systemStatus?.database || "PostgreSQL"} ({healthStatus?.database || "Ulanmoqda"})
                  </span>
                </div>
                <span className="text-xs text-ink-faint">
                  Profil: <strong className="text-ink">{systemStatus?.deployment_profile || "Standart"}</strong>
                </span>
              </Card>

              <Card className="p-4 flex flex-col gap-2">
                <div className="flex items-center justify-between text-xs text-ink-muted">
                  <span>Tizim holati</span>
                  <Server size={16} className="text-primary" />
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className={cn(
                      "h-2.5 w-2.5 rounded-full",
                      healthStatus?.status === "ok" ? "bg-emerald-500" : "bg-warning"
                    )}
                  />
                  <span className="text-lg font-bold uppercase text-ink">
                    {healthStatus?.status || "Aktiv"}
                  </span>
                </div>
                <span className="text-xs text-ink-faint">
                  Muhit: <strong className="text-ink">{systemStatus?.environment || "development"}</strong>
                </span>
              </Card>

              <Card className="p-4 flex flex-col gap-2">
                <div className="flex items-center justify-between text-xs text-ink-muted">
                  <span>AI Provayderlari</span>
                  <Cpu size={16} className="text-primary" />
                </div>
                <span className="text-lg font-bold text-ink">
                  {systemStatus?.offline_mode
                    ? "Offline rejim"
                    : `${systemStatus?.providers.filter((p) => p.configured).length || 0} ta sozlangan`}
                </span>
                <span className="text-xs text-ink-faint">
                  {systemStatus?.providers.map((p) => p.name).join(", ") || "Mahalliy"}
                </span>
              </Card>

              <Card className="p-4 flex flex-col gap-2">
                <div className="flex items-center justify-between text-xs text-ink-muted">
                  <span>Versiya</span>
                  <Activity size={16} className="text-primary" />
                </div>
                <span className="text-lg font-bold font-mono text-ink">
                  v{systemStatus?.version || "0.2.0"}
                </span>
                <span className="text-xs text-ink-faint">
                  Xavfsizlik audit loglari: <strong>Durable</strong>
                </span>
              </Card>
            </div>

            {/* Registered Agents Catalog */}
            <Card className="p-5 flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-semibold text-ink flex items-center gap-2">
                    <Bot size={18} className="text-primary" />
                    Ro‘yxatdan o‘tgan Agentlar katalogi
                  </h3>
                  <p className="text-xs text-ink-muted mt-0.5">
                    Tizimda faoliyat yurituvchi aqlli agentlar va ularning statusi
                  </p>
                </div>
                <span className="text-xs px-2.5 py-1 rounded-md bg-surface-2 border border-line text-ink-muted font-mono">
                  Jami: {systemStatus?.agents.length || 0} ta
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {(systemStatus?.agents || []).map((agent) => (
                  <div
                    key={agent.key}
                    className="p-3 rounded-xl border border-line bg-surface flex flex-col gap-2 transition-all hover:border-line-hover"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-sm text-ink capitalize">
                        {agent.names?.uz || agent.key}
                      </span>
                      <span
                        className={cn(
                          "px-2 py-0.5 text-xs rounded-full font-medium border",
                          agent.available
                            ? "bg-emerald-500/10 text-emerald-600 border-emerald-500/20"
                            : "bg-surface-3 text-ink-faint border-line"
                        )}
                      >
                        {agent.available ? "Faol" : "O‘chirilgan"}
                      </span>
                    </div>
                    <p className="text-xs text-ink-muted line-clamp-2">
                      {agent.description}
                    </p>
                    <div className="flex items-center justify-between text-xs text-ink-faint pt-2 border-t border-line/60">
                      <span>Kalit: <strong className="font-mono">{agent.key}</strong></span>
                      <span className="capitalize">{agent.maturity || "v1"}</span>
                    </div>
                  </div>
                ))}
              </div>
            </Card>

            {/* Governed Architecture Improvement Proposals (AuditLog-backed) */}
            <Card className="p-5 flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-semibold text-ink flex items-center gap-2">
                    <FileText size={18} className="text-primary" />
                    Boshqariladigan Arxitektura Takliflari (Durable Proposals)
                  </h3>
                  <p className="text-xs text-ink-muted mt-0.5">
                    Tizim yaxshilanishlari AuditLog orqali saqlanadi va inson tomonidan tasdiqlanishi shart
                  </p>
                </div>
              </div>

              {proposals.length === 0 ? (
                <div className="p-8 text-center text-ink-muted border border-dashed border-line rounded-xl">
                  <p className="text-sm">Hozircha ko‘rib chiqilmagan yangi arxitektura takliflari mavjud emas.</p>
                  <p className="text-xs text-ink-faint mt-1">
                    Barcha amallar to‘g‘ridan-to‘g‘ri ma&apos;lumotlar bazasining AuditLog jadvalida qayd etiladi.
                  </p>
                </div>
              ) : (
                <div className="flex flex-col gap-3">
                  {proposals.map((prop) => (
                    <div
                      key={prop.id}
                      className="p-4 rounded-xl border border-line bg-surface flex flex-col gap-3"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <h4 className="font-medium text-sm text-ink">{prop.goal}</h4>
                          <p className="text-xs font-mono text-ink-faint mt-0.5">
                            ID: {prop.id} | SHA256: {prop.sha256.slice(0, 16)}...
                          </p>
                        </div>
                        <span
                          className={cn(
                            "px-2.5 py-0.5 text-xs rounded-full font-medium border",
                            prop.status === "proposal_only"
                              ? "bg-amber-500/10 text-amber-600 border-amber-500/20"
                              : prop.decision === "request_independent_review"
                              ? "bg-blue-500/10 text-blue-600 border-blue-500/20"
                              : "bg-surface-3 text-ink-faint border-line"
                          )}
                        >
                          {prop.decision || prop.status}
                        </span>
                      </div>

                      <div className="flex items-center justify-between pt-2 border-t border-line text-xs">
                        <span className="text-ink-faint flex items-center gap-1">
                          <Lock size={12} />
                          Sandbox tested: <strong>{prop.sandbox_tested ? "Ha" : "Yo‘q"}</strong> | 
                          Execution authorized: <strong>{prop.execution_authorized ? "Ha" : "Bloklangan"}</strong>
                        </span>

                        <div className="flex items-center gap-2">
                          <Button
                            variant="secondary"
                            className="text-xs h-7 px-2.5 text-danger hover:bg-danger/10"
                            disabled={actingProposalId === prop.id}
                            onClick={() => void handleDecision(prop, "reject")}
                          >
                            <XCircle size={14} className="mr-1" />
                            Rad etish
                          </Button>
                          <Button
                            variant="primary"
                            className="text-xs h-7 px-2.5"
                            disabled={actingProposalId === prop.id}
                            onClick={() => void handleDecision(prop, "request_independent_review")}
                          >
                            <CheckCircle2 size={14} className="mr-1" />
                            Mustaqil ko‘rib chiqishni talab qilish
                          </Button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </>
        )}
      </div>
    </PageFrame>
  );
}
