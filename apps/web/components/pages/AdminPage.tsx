"use client";

import { Button, Card, cn, Spinner } from "@ezo/ui";
import {
  Activity,
  AlertTriangle,
  Bot,
  CheckCircle2,
  Cpu,
  Database,
  DollarSign,
  FileText,
  HardDrive,
  Lock,
  RefreshCw,
  Save,
  Server,
  ShieldAlert,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiUrl, storedToken } from "@/lib/api";
import { useI18n } from "@/lib/i18n/context";
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

interface AgentConfig {
  agent_id: string;
  name: string;
  description: string;
  model: string;
  max_tokens: number;
  temperature: number;
  rate_limit_per_min: number;
  enabled: boolean;
  allowed_roles: string[];
}

interface SystemHealth {
  status: string;
  uptime_seconds: number;
  db_status: string;
  worker_status: string;
  memory_usage_mb: number;
  api_version: string;
  active_sessions: number;
}

interface K8Proposal {
  id: string;
  title: string;
  description: string;
  category: string;
  status: "pending" | "approved" | "rejected";
  proposed_by: string;
  created_at: string;
  review_notes?: string | null;
}

interface AuditLog {
  id: string;
  timestamp: string;
  user_identifier: string;
  action: string;
  resource: string;
  status: string;
  ip_masked: string;
}

interface ResourceBudget {
  daily_token_budget: number;
  tokens_consumed_today: number;
  monthly_spend_limit_usd: number;
  current_spend_usd: number;
  storage_quota_mb: number;
  storage_used_mb: number;
}

export function AdminPage() {
  const { m } = useI18n();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  // Governance data
  const [govStatus, setGovStatus] = useState<GovernanceStatus | null>(null);
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [proposals, setProposals] = useState<K8Proposal[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [budgets, setBudgets] = useState<ResourceBudget | null>(null);

  // Active review notes
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const [savingAgent, setSavingAgent] = useState<string | null>(null);

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

      // Check governance status
      const statusRes = await fetch(`${apiUrl()}/api/admin/governance/status`, { headers });
      if (statusRes.status === 403) {
        setForbidden(true);
        setLoading(false);
        return;
      }
      if (!statusRes.ok) throw new Error(`HTTP ${statusRes.status}`);
      const statusData = (await statusRes.json()) as GovernanceStatus;
      setGovStatus(statusData);

      // Load health
      const healthRes = await fetch(`${apiUrl()}/api/admin/governance/system-health`, { headers });
      if (healthRes.ok) setHealth((await healthRes.json()) as SystemHealth);

      // Load agents
      const agentsRes = await fetch(`${apiUrl()}/api/admin/governance/agents`, { headers });
      if (agentsRes.ok) setAgents((await agentsRes.json()) as AgentConfig[]);

      // Load proposals
      const propRes = await fetch(`${apiUrl()}/api/admin/governance/proposals`, { headers });
      if (propRes.ok) setProposals((await propRes.json()) as K8Proposal[]);

      // Load audit logs
      const auditRes = await fetch(`${apiUrl()}/api/admin/governance/audit-logs`, { headers });
      if (auditRes.ok) setAuditLogs((await auditRes.json()) as AuditLog[]);

      // Load budgets
      const budgetRes = await fetch(`${apiUrl()}/api/admin/governance/budgets`, { headers });
      if (budgetRes.ok) setBudgets((await budgetRes.json()) as ResourceBudget);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [authHeaders]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  async function handleReview(proposalId: string, action: "approve" | "reject") {
    const notes = reviewNotes[proposalId] || (action === "approve" ? "Tasdiqlandi" : "Rad etildi");
    try {
      const res = await fetch(`${apiUrl()}/api/admin/governance/proposals/${proposalId}/review`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ action, notes }),
      });
      if (res.ok) {
        const updated = (await res.json()) as K8Proposal;
        setProposals((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
      }
    } catch {
      // Ignored
    }
  }

  async function handleUpdateAgent(agent: AgentConfig) {
    setSavingAgent(agent.agent_id);
    try {
      const res = await fetch(`${apiUrl()}/api/admin/governance/agents/${agent.agent_id}`, {
        method: "PUT",
        headers: authHeaders(),
        body: JSON.stringify({
          model: agent.model,
          max_tokens: agent.max_tokens,
          temperature: agent.temperature,
          rate_limit_per_min: agent.rate_limit_per_min,
          enabled: agent.enabled,
        }),
      });
      if (res.ok) {
        const updated = (await res.json()) as AgentConfig;
        setAgents((prev) => prev.map((a) => (a.agent_id === updated.agent_id ? updated : a)));
      }
    } finally {
      setSavingAgent(null);
    }
  }

  return (
    <PageFrame
      title={m.governance?.title ?? "Super Admin va Boshqaruv"}
      subtitle={m.governance?.subtitle ?? "Tizim holati, agent marshrutlash, xavfsizlik va resurs byudjetlari monitoringi."}
      actions={
        <Button
          variant="secondary"
          size="sm"
          icon={<RefreshCw size={14} className={loading ? "animate-spin" : ""} />}
          onClick={() => void loadData()}
        >
          {m.common?.retry ?? "Yangilash"}
        </Button>
      }
    >
      {/* 403 Forbidden State */}
      {forbidden && (
        <Card className="border-red-500/30 bg-red-500/5 p-6 text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-red-500/10 text-red-500">
            <ShieldAlert size={28} />
          </div>
          <h3 className="text-base font-semibold text-ink">
            {m.governance?.forbiddenTitle ?? "Ruxsat berilmagan (403 Forbidden)"}
          </h3>
          <p className="mt-2 text-sm text-ink-muted">
            {m.governance?.forbiddenBody ??
              "Ushbu sahifaga faqat platforma Super Admin foydalanuvchisi kirishi mumkin."}
          </p>
          <div className="mx-auto mt-4 max-w-md rounded-xl border border-line bg-surface p-3 text-left text-xs leading-relaxed text-ink-faint">
            <p className="font-semibold text-ink">Xavfsizlik qoidasi (RBAC):</p>
            <p className="mt-1">
              Foydalanuvchining obuna darajasi (Pro, Enterprise) platforma boshqaruv huquqini bermaydi. Barcha
              governance API so‘rovlari server tomonida qat'iy tekshiriladi.
            </p>
          </div>
        </Card>
      )}

      {loading && !forbidden && (
        <div className="flex h-64 items-center justify-center">
          <Spinner />
        </div>
      )}

      {error && !forbidden && (
        <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-sm text-red-600">
          {error}
        </div>
      )}

      {!loading && !forbidden && (
        <div className="space-y-6">
          {/* Super Admin Status Banner */}
          <Card className="border-accent/30 bg-accent/5">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="rounded-xl bg-accent/20 p-2 text-accent">
                  <ShieldCheck size={24} />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-ink">
                      {govStatus?.super_admin_verified ? "Super Admin: Autentifikatsiya Tasdiqlangan" : "Kutilmoqda"}
                    </span>
                    <span className="rounded-full bg-accent/20 px-2 py-0.5 text-[11px] font-semibold text-accent">
                      {govStatus?.governance_mode ?? "human_governed"}
                    </span>
                  </div>
                  <p className="mt-0.5 text-xs text-ink-muted">
                    {m.governance?.rbacNotice ??
                      "Faqat Super Admin rolidagi akkauntlar uchun ruxsat etilgan. Obuna darajasi platforma boshqaruv huquqini bermaydi."}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2 text-xs">
                <span className="flex items-center gap-1 rounded-md bg-surface px-2.5 py-1 text-ink-faint">
                  <Lock size={12} className="text-success" /> Kod o&apos;zgartirish: Bloklangan
                </span>
                <span className="flex items-center gap-1 rounded-md bg-surface px-2.5 py-1 text-ink-faint">
                  <Lock size={12} className="text-success" /> Avto-Deploy: Bloklangan
                </span>
              </div>
            </div>
          </Card>

          {/* System Health Overview */}
          <section>
            <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
              <Activity size={16} className="text-accent" />
              {m.governance?.systemHealth ?? "Tizim salomatligi"}
            </h3>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="rounded-xl border border-line bg-surface p-3.5">
                <div className="flex items-center justify-between text-xs text-ink-muted">
                  <span>API Holati</span>
                  <Server size={14} className="text-success" />
                </div>
                <p className="mt-1 text-base font-bold text-success capitalize">{health?.status ?? "Normal"}</p>
                <span className="text-[11px] text-ink-faint">v{health?.api_version ?? "0.2.0"}</span>
              </div>
              <div className="rounded-xl border border-line bg-surface p-3.5">
                <div className="flex items-center justify-between text-xs text-ink-muted">
                  <span>Ma&apos;lumotlar bazasi</span>
                  <Database size={14} className="text-accent" />
                </div>
                <p className="mt-1 text-base font-bold text-ink">{health?.db_status ?? "Uланган"}</p>
                <span className="text-[11px] text-ink-faint">PostgreSQL / SQLite</span>
              </div>
              <div className="rounded-xl border border-line bg-surface p-3.5">
                <div className="flex items-center justify-between text-xs text-ink-muted">
                  <span>Durable Worker</span>
                  <Cpu size={14} className="text-accent2" />
                </div>
                <p className="mt-1 text-base font-bold text-ink">{health?.worker_status ?? "Faol"}</p>
                <span className="text-[11px] text-ink-faint">Izolyatsiya qilingan text worker</span>
              </div>
              <div className="rounded-xl border border-line bg-surface p-3.5">
                <div className="flex items-center justify-between text-xs text-ink-muted">
                  <span>Operativ xotira (RAM)</span>
                  <HardDrive size={14} className="text-ink-muted" />
                </div>
                <p className="mt-1 text-base font-bold text-ink">
                  {health?.memory_usage_mb ? `${health.memory_usage_mb.toFixed(1)} MB` : "148.5 MB"}
                </p>
                <span className="text-[11px] text-ink-faint">{health?.active_sessions ?? 14} faol sessiya</span>
              </div>
            </div>
          </section>

          {/* Resource & Spending Budgets */}
          <section>
            <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
              <DollarSign size={16} className="text-success" />
              {m.governance?.budgets ?? "Resurslar va xarajat byudjeti"}
            </h3>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div className="rounded-xl border border-line bg-surface p-4">
                <p className="text-xs text-ink-muted">Kunlik Token Limiti</p>
                <div className="mt-2 flex items-baseline justify-between">
                  <span className="text-lg font-bold text-ink">
                    {budgets?.tokens_consumed_today.toLocaleString() ?? 0}
                  </span>
                  <span className="text-xs text-ink-faint">
                    / {budgets?.daily_token_budget.toLocaleString() ?? "1,000,000"}
                  </span>
                </div>
                <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
                  <div
                    className="h-full bg-accent"
                    style={{
                      width: `${Math.min(
                        100,
                        ((budgets?.tokens_consumed_today ?? 0) / (budgets?.daily_token_budget ?? 1)) * 100
                      )}%`,
                    }}
                  />
                </div>
              </div>
              <div className="rounded-xl border border-line bg-surface p-4">
                <p className="text-xs text-ink-muted">Oylik Xarajat Chegarasi</p>
                <div className="mt-2 flex items-baseline justify-between">
                  <span className="text-lg font-bold text-success">
                    ${budgets?.current_spend_usd.toFixed(2) ?? "0.00"}
                  </span>
                  <span className="text-xs text-ink-faint">
                    / ${budgets?.monthly_spend_limit_usd.toFixed(2) ?? "250.00"}
                  </span>
                </div>
                <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
                  <div
                    className="h-full bg-success"
                    style={{
                      width: `${Math.min(
                        100,
                        ((budgets?.current_spend_usd ?? 0) / (budgets?.monthly_spend_limit_usd ?? 1)) * 100
                      )}%`,
                    }}
                  />
                </div>
              </div>
              <div className="rounded-xl border border-line bg-surface p-4">
                <p className="text-xs text-ink-muted">Hujjatlar Saqlash Hajmi</p>
                <div className="mt-2 flex items-baseline justify-between">
                  <span className="text-lg font-bold text-ink">
                    {budgets?.storage_used_mb ?? 0} MB
                  </span>
                  <span className="text-xs text-ink-faint">
                    / {budgets?.storage_quota_mb ?? 10000} MB
                  </span>
                </div>
                <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
                  <div
                    className="h-full bg-accent2"
                    style={{
                      width: `${Math.min(
                        100,
                        ((budgets?.storage_used_mb ?? 0) / (budgets?.storage_quota_mb ?? 1)) * 100
                      )}%`,
                    }}
                  />
                </div>
              </div>
            </div>
          </section>

          {/* Agent Settings & Operational Controls */}
          <section>
            <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
              <Bot size={16} className="text-accent2" />
              {m.governance?.agentSettings ?? "Agentlar sozlamalari"}
            </h3>
            <div className="grid gap-3">
              {agents.map((agent) => (
                <div
                  key={agent.agent_id}
                  className="flex flex-col gap-3 rounded-xl border border-line bg-surface p-4 md:flex-row md:items-center md:justify-between"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-ink">{agent.name}</span>
                      <span className="rounded bg-surface-2 px-1.5 py-0.5 text-[11px] font-mono text-ink-muted">
                        {agent.agent_id}
                      </span>
                    </div>
                    <p className="text-xs text-ink-muted">{agent.description}</p>
                    <div className="flex flex-wrap gap-2 text-[11px] text-ink-faint">
                      <span>Rollar: {agent.allowed_roles.join(", ")}</span>
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-3">
                    <label className="text-xs text-ink-muted">
                      Model:
                      <input
                        className="ml-1.5 rounded-lg border border-line bg-surface-2 px-2 py-1 text-xs text-ink"
                        value={agent.model}
                        onChange={(e) => {
                          const val = e.target.value;
                          setAgents((prev) =>
                            prev.map((a) => (a.agent_id === agent.agent_id ? { ...a, model: val } : a))
                          );
                        }}
                      />
                    </label>
                    <label className="text-xs text-ink-muted">
                      Max tokens:
                      <input
                        type="number"
                        className="ml-1.5 w-20 rounded-lg border border-line bg-surface-2 px-2 py-1 text-xs text-ink"
                        value={agent.max_tokens}
                        onChange={(e) => {
                          const val = Number(e.target.value);
                          setAgents((prev) =>
                            prev.map((a) => (a.agent_id === agent.agent_id ? { ...a, max_tokens: val } : a))
                          );
                        }}
                      />
                    </label>
                    <label className="text-xs text-ink-muted">
                      Limit/daq:
                      <input
                        type="number"
                        className="ml-1.5 w-16 rounded-lg border border-line bg-surface-2 px-2 py-1 text-xs text-ink"
                        value={agent.rate_limit_per_min}
                        onChange={(e) => {
                          const val = Number(e.target.value);
                          setAgents((prev) =>
                            prev.map((a) =>
                              a.agent_id === agent.agent_id ? { ...a, rate_limit_per_min: val } : a
                            )
                          );
                        }}
                      />
                    </label>
                    <Button
                      size="sm"
                      variant="primary"
                      icon={<Save size={12} />}
                      disabled={savingAgent === agent.agent_id}
                      onClick={() => void handleUpdateAgent(agent)}
                    >
                      {savingAgent === agent.agent_id ? "Saqlanmoqda..." : "Saqlash"}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* K8 Architecture & Security Proposals */}
          <section>
            <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
              <FileText size={16} className="text-accent" />
              {m.governance?.proposals ?? "Arxitektura va K8 takliflari"}
            </h3>
            <div className="space-y-3">
              {proposals.map((prop) => (
                <div key={prop.id} className="rounded-xl border border-line bg-surface p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-ink">{prop.title}</span>
                      <span
                        className={cn(
                          "rounded-full px-2 py-0.5 text-[11px] font-semibold",
                          prop.status === "approved"
                            ? "bg-success/15 text-success"
                            : prop.status === "rejected"
                            ? "bg-red-500/15 text-red-500"
                            : "bg-accent/15 text-accent"
                        )}
                      >
                        {prop.status}
                      </span>
                    </div>
                    <span className="text-[11px] text-ink-faint">{prop.created_at}</span>
                  </div>
                  <p className="mt-1 text-xs text-ink-muted">{prop.description}</p>
                  {prop.review_notes && (
                    <p className="mt-2 rounded-lg bg-surface-2 p-2 text-xs text-ink-faint">
                      <strong>Ko&apos;rib chiqish izohi:</strong> {prop.review_notes}
                    </p>
                  )}
                  {prop.status === "pending" && (
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <input
                        placeholder="Ko'rib chiqish izohi..."
                        className="flex-1 rounded-lg border border-line bg-surface-2 px-3 py-1.5 text-xs text-ink"
                        value={reviewNotes[prop.id] || ""}
                        onChange={(e) => setReviewNotes({ ...reviewNotes, [prop.id]: e.target.value })}
                      />
                      <Button
                        size="sm"
                        variant="primary"
                        icon={<CheckCircle2 size={12} />}
                        onClick={() => void handleReview(prop.id, "approve")}
                      >
                        {m.governance?.approve ?? "Tasdiqlash"}
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        icon={<XCircle size={12} />}
                        onClick={() => void handleReview(prop.id, "reject")}
                      >
                        {m.governance?.reject ?? "Rad etish"}
                      </Button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>

          {/* Sanitized Audit Logs */}
          <section>
            <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
              <ShieldCheck size={16} className="text-ink-muted" />
              {m.governance?.auditLogs ?? "Xavfsizlik va audit jurnali"}
            </h3>
            <div className="overflow-x-auto rounded-xl border border-line bg-surface">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-line bg-surface-2 text-ink-muted">
                  <tr>
                    <th className="p-3">Vaqt</th>
                    <th className="p-3">Foydalanuvchi</th>
                    <th className="p-3">Amal</th>
                    <th className="p-3">Resurs</th>
                    <th className="p-3">Holat</th>
                    <th className="p-3">IP (Niqoblangan)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line text-ink">
                  {auditLogs.map((log) => (
                    <tr key={log.id} className="hover:bg-surface-2/40">
                      <td className="p-3 font-mono text-[11px] text-ink-faint">
                        {log.timestamp.slice(0, 19).replace("T", " ")}
                      </td>
                      <td className="p-3">{log.user_identifier}</td>
                      <td className="p-3 font-semibold">{log.action}</td>
                      <td className="p-3 font-mono text-[11px] text-ink-muted">{log.resource}</td>
                      <td className="p-3">
                        <span className="rounded bg-success/15 px-1.5 py-0.5 text-[10px] font-semibold text-success">
                          {log.status}
                        </span>
                      </td>
                      <td className="p-3 font-mono text-[11px] text-ink-faint">{log.ip_masked}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}
    </PageFrame>
  );
}
