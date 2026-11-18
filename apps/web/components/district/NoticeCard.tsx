"use client";

import type { DistrictNotice } from "@ezo/shared";
import { Button } from "@ezo/ui";
import { MessageSquareWarning, Send, X } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n/context";

const CHANNEL_NAMES: Record<string, string> = { telegram: "Telegram", sms: "SMS" };

/** The state line of a notice: "SMS: delivered (id …)" / "Telegram: error — …". */
export function resultLines(
  notice: DistrictNotice,
  t: { result: string; ok: string; err: string; unknown: string },
  f: (template: string, values: Record<string, string | number>) => string,
): string[] {
  return Object.entries(notice.results ?? {}).map(([channel, r]) =>
    f(t.result, {
      channel: CHANNEL_NAMES[channel] ?? channel,
      state: r.ok
        ? f(t.ok, { id: String(r.id ?? "") })
        : r.unknown
          ? t.unknown
          : f(t.err, { error: r.error ?? "" }),
    }),
  );
}

/**
 * A warning to one responsible person. A draft shows its exact text (editable) and is sent
 * only when the owner presses "Send" and confirms; the card then shows each channel's real
 * result from the server, never an assumed one.
 */
export function NoticeCard({
  notice: initial,
  canSend = true,
  onChanged,
}: {
  notice: DistrictNotice;
  canSend?: boolean;
  onChanged?: (notice: DistrictNotice) => void;
}) {
  const { m, f } = useI18n();
  const t = m.district;
  const [notice, setNotice] = useState(initial);
  const [text, setText] = useState(initial.text);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const channels = notice.channels.map((c) => CHANNEL_NAMES[c] ?? c).join(" + ");
  const statusLabel = {
    draft: t.draft,
    sent: t.sent,
    partly_sent: t.partlySent,
    failed: t.failed,
    cancelled: t.cancelled,
  }[notice.status];

  async function act(run: () => Promise<DistrictNotice>) {
    setBusy(true);
    setError(null);
    try {
      const next = await run();
      setNotice(next);
      onChanged?.(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-3 rounded-xl border border-line bg-surface-raised p-3 text-sm" data-testid="district-notice">
      <div className="flex flex-wrap items-center gap-2">
        <MessageSquareWarning size={16} className="text-accent" />
        <span className="font-medium">{f(t.to, { name: notice.recipient_name })}</span>
        <span
          className={`rounded-full px-2 py-0.5 text-xs ${notice.status === "sent" ? "bg-success/15 text-success" : notice.status === "draft" ? "bg-accent/10 text-accent" : "bg-danger/10 text-danger"}`}
          data-testid="notice-status"
        >
          {statusLabel}
        </span>
        <span className="text-xs text-ink-faint">{channels ? f(t.via, { channels }) : t.noChannel}</span>
      </div>
      {notice.status === "draft" ? (
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={4}
          maxLength={900}
          className="mt-2 w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-accent"
          data-testid="notice-text"
        />
      ) : (
        <p className="mt-2 whitespace-pre-wrap text-ink-soft">{notice.text}</p>
      )}
      <p className="mt-1 text-xs text-ink-faint">{f(t.sender, { sender: notice.sender })}</p>
      {resultLines(notice, t, f).map((line) => (
        <p key={line} className="mt-1 text-xs" data-testid="notice-result">
          {line}
        </p>
      ))}
      {error ? <p className="mt-1 text-xs text-danger">{error}</p> : null}
      {notice.status === "draft" ? (
        <div className="mt-2 flex flex-wrap gap-2">
          {canSend ? (
            <Button
              size="sm"
              disabled={busy || !notice.channels.length || text.trim().length < 10}
              onClick={() => {
                if (!window.confirm(f(t.confirmSend, { name: notice.recipient_name, channels }))) return;
                void act(() => api.sendDistrictNotice(notice.id, text.trim() === notice.text ? undefined : text.trim()));
              }}
              data-testid="notice-send"
            >
              <Send size={14} /> {busy ? t.sending : t.send}
            </Button>
          ) : (
            <span className="text-xs text-ink-faint">{t.ownerOnly}</span>
          )}
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => void act(() => api.cancelDistrictNotice(notice.id))}>
            <X size={14} /> {t.cancel}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
