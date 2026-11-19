"use client";

import { Button, Card, TextField } from "@ezo/ui";
import { useEffect, useState } from "react";
import { api, storedToken } from "@/lib/api";
import { useI18n } from "@/lib/i18n/context";

function Frame({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex min-h-full items-center justify-center p-4">
      <Card className="w-full max-w-md p-6">
        <h1 className="mb-3 text-xl font-semibold">{title}</h1>
        {children}
      </Card>
    </div>
  );
}

const done = (token: string) => {
  storedToken.set(token);
  // A full reload, so every page starts again with the new account's token.
  window.location.replace(`${window.location.origin}/`);
};

/** /join#code=…: an invited employee sets their own password (the code never leaves the fragment until sent). */
export function JoinPage() {
  const { m, f } = useI18n();
  const t = m.auth;
  const [code, setCode] = useState<string | null>(null);
  const [who, setWho] = useState<{ email: string; display_name: string } | null>(null);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const found = new URLSearchParams(window.location.hash.slice(1)).get("code");
    void Promise.resolve().then(() => {
      setCode(found ?? "");
      if (found) {
        api
          .inviteInfo(found)
          .then(setWho)
          .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
      }
    });
  }, []);

  return (
    <Frame title={t.joinTitle}>
      {code === "" ? <p className="text-sm text-danger">{t.noCode}</p> : null}
      {who ? <p className="mb-4 text-sm text-ink-muted">{f(t.joinFor, { name: who.display_name, email: who.email })}</p> : null}
      {error ? <p className="mb-3 text-sm text-danger" role="alert">{error}</p> : null}
      {who && code ? (
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (password !== confirm) {
              setError(t.mismatch);
              return;
            }
            setBusy(true);
            setError(null);
            api
              .acceptInvite(code, password)
              .then((r) => done(r.token))
              .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)))
              .finally(() => setBusy(false));
          }}
        >
          <TextField label={t.password} type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} data-testid="join-password" />
          <TextField label={t.confirm} type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required minLength={8} data-testid="join-confirm" />
          <Button type="submit" disabled={busy} data-testid="join-submit">
            {t.join}
          </Button>
        </form>
      ) : null}
    </Frame>
  );
}

/** /login: an invited employee signs in with email and password. */
export function LoginPage() {
  const { m } = useI18n();
  const t = m.auth;
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <Frame title={t.loginTitle}>
      <p className="mb-4 text-sm text-ink-muted">{t.loginSubtitle}</p>
      {error ? <p className="mb-3 text-sm text-danger" role="alert">{error}</p> : null}
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          setBusy(true);
          setError(null);
          api
            .login(email, password)
            .then((r) => done(r.token))
            .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)))
            .finally(() => setBusy(false));
        }}
      >
        <TextField label={t.email} type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required data-testid="login-email" />
        <TextField label={t.loginPassword} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required data-testid="login-password" />
        <Button type="submit" disabled={busy} data-testid="login-submit">
          {t.login}
        </Button>
      </form>
    </Frame>
  );
}
