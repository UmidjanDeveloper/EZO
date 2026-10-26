"use client";

import { Button, Card } from "@ezo/ui";
import { KeyRound, UserPlus, Users } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiUrl, storedToken } from "@/lib/api";
import { useI18n } from "@/lib/i18n/context";

// Owner-managed accounts (P8 foundation). The server enforces everything: only the
// Super Admin may call these routes, a tier never grants authority, and a token secret
// is returned exactly once and never stored.

interface Account {
  id: string;
  email: string;
  display_name: string;
  role: string;
  tier: "free" | "pro" | "premium";
  status: "active" | "disabled";
}

interface AccountToken {
  id: string;
  label: string;
  expires_at: string | null;
  last_used_at: string | null;
  revoked: boolean;
}

const TIERS = ["free", "pro", "premium"] as const;

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = storedToken.get().trim();
  const res = await fetch(`${apiUrl()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { error?: { message?: string } };
    throw new Error(body.error?.message ?? `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

export function AccountsPanel() {
  const { m, f } = useI18n();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [tokens, setTokens] = useState<Record<string, AccountToken[]>>({});
  const [secret, setSecret] = useState<{ email: string; token: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [tier, setTier] = useState<Account["tier"]>("free");

  const reload = useCallback(
    () =>
      call<Account[]>("/api/admin/users")
        .then(setAccounts)
        .catch((e: Error) => setError(e.message)),
    []
  );

  useEffect(() => {
    void reload();
  }, [reload]);

  const run = (action: Promise<unknown>) =>
    action
      .then(() => {
        setError(null);
        return reload();
      })
      .catch((e: Error) => setError(e.message));

  const loadTokens = (id: string) =>
    call<AccountToken[]>(`/api/admin/users/${id}/tokens`)
      .then((list) => setTokens((t) => ({ ...t, [id]: list })))
      .catch((e: Error) => setError(e.message));

  const issue = (account: Account) =>
    call<{ token: string }>(`/api/admin/users/${account.id}/tokens`, {
      method: "POST",
      body: JSON.stringify({ label: "EZO" }),
    })
      .then((r) => {
        setSecret({ email: account.email, token: r.token });
        return loadTokens(account.id);
      })
      .catch((e: Error) => setError(e.message));

  return (
    <Card className="p-5 flex flex-col gap-4" data-testid="accounts-panel">
      <div>
        <h3 className="font-semibold text-ink flex items-center gap-2">
          <Users size={18} className="text-primary" />
          {m.accounts.title}
        </h3>
        <p className="text-xs text-ink-muted mt-0.5">
          {m.accounts.subtitle}
        </p>
      </div>

      {error && <p className="text-sm text-danger" role="alert">{error}</p>}

      {secret && (
        <div className="p-3 rounded-xl border border-warning/40 bg-warning/5 text-sm" data-testid="account-secret">
          <p className="text-ink">
            <strong>{secret.email}</strong> {m.accounts.secretAfterEmail}
          </p>
          <code className="block mt-2 break-all font-mono text-xs text-ink">{secret.token}</code>
          <Button variant="secondary" className="mt-2 h-7 text-xs" onClick={() => setSecret(null)}>
            {m.accounts.hide}
          </Button>
        </div>
      )}

      <form
        className="flex flex-col sm:flex-row gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void run(
            call("/api/admin/users", {
              method: "POST",
              body: JSON.stringify({ email, display_name: name || email, tier }),
            }).then(() => {
              setEmail("");
              setName("");
            })
          );
        }}
      >
        <input
          className="flex-1 rounded-lg border border-line bg-surface px-3 py-2 text-sm"
          placeholder={m.accounts.emailLabel}
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          aria-label={m.accounts.emailLabel}
        />
        <input
          className="flex-1 rounded-lg border border-line bg-surface px-3 py-2 text-sm"
          placeholder={m.accounts.nameLabel}
          value={name}
          onChange={(e) => setName(e.target.value)}
          aria-label={m.accounts.nameLabel}
        />
        <select
          className="rounded-lg border border-line bg-surface px-3 py-2 text-sm"
          value={tier}
          onChange={(e) => setTier(e.target.value as Account["tier"])}
          aria-label={m.accounts.tierLabel}
        >
          {TIERS.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <Button type="submit" className="gap-1">
          <UserPlus size={14} />
          {m.accounts.add}
        </Button>
      </form>

      <ul className="flex flex-col gap-2">
        {accounts.map((a) => (
          <li key={a.id} className="p-3 rounded-xl border border-line bg-surface flex flex-col gap-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm text-ink">
                <strong>{a.display_name}</strong> · {a.email} ·{" "}
                <span className="font-mono text-xs">{a.role}</span>
              </span>
              {a.role === "super_admin" ? (
                <span className="text-xs text-ink-faint">{m.accounts.ownerUnlimited}</span>
              ) : (
                <div className="flex flex-wrap items-center gap-2">
                  <select
                    className="rounded-md border border-line bg-surface px-2 py-1 text-xs"
                    value={a.tier}
                    aria-label={f(m.accounts.tierOf, { email: a.email })}
                    onChange={(e) =>
                      void run(
                        call(`/api/admin/users/${a.id}`, {
                          method: "PATCH",
                          body: JSON.stringify({ tier: e.target.value }),
                        })
                      )
                    }
                  >
                    {TIERS.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                  <Button
                    variant="secondary"
                    className="h-7 text-xs"
                    onClick={() =>
                      void run(
                        call(`/api/admin/users/${a.id}`, {
                          method: "PATCH",
                          body: JSON.stringify({
                            status: a.status === "active" ? "disabled" : "active",
                          }),
                        })
                      )
                    }
                  >
                    {a.status === "active" ? m.accounts.disable : m.accounts.enable}
                  </Button>
                  {a.status === "active" && (
                    <Button variant="secondary" className="h-7 text-xs gap-1" onClick={() => void issue(a)}>
                      <KeyRound size={12} />
                      {m.accounts.issueToken}
                    </Button>
                  )}
                  <Button variant="secondary" className="h-7 text-xs" onClick={() => void loadTokens(a.id)}>
                    {m.accounts.tokens}
                  </Button>
                </div>
              )}
            </div>
            {tokens[a.id]?.map((t) => (
              <div key={t.id} className="flex items-center justify-between text-xs text-ink-muted pl-2">
                <span>
                  {t.label} ·{" "}
                  {t.revoked
                    ? m.accounts.tokenRevoked
                    : f(m.accounts.tokenExpires, {
                        date: t.expires_at?.slice(0, 10) ?? m.accounts.tokenNoExpiry,
                      })}
                  {t.last_used_at ? ` · ${f(m.accounts.tokenLastUsed, { date: t.last_used_at.slice(0, 10) })}` : ""}
                </span>
                {!t.revoked && (
                  <Button
                    variant="secondary"
                    className="h-6 text-xs text-danger"
                    onClick={() =>
                      void call(`/api/admin/users/${a.id}/tokens/${t.id}`, { method: "DELETE" })
                        .then(() => loadTokens(a.id))
                        .catch((e: Error) => setError(e.message))
                    }
                  >
                    {m.accounts.revoke}
                  </Button>
                )}
              </div>
            ))}
          </li>
        ))}
      </ul>
    </Card>
  );
}
