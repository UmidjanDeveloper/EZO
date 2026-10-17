"use client";

import { cn } from "@ezo/ui";
import { Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useApp } from "@/lib/app-state";
import { useI18n } from "@/lib/i18n/context";
import { MODULE_META, NAV_ORDER } from "@/lib/modules";
import { EzoOrb } from "../common/EzoOrb";

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { m } = useI18n();
  const pathname = usePathname();
  const router = useRouter();
  const { conversations, refreshConversations } = useApp();

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" || pathname.startsWith("/chat") : pathname.startsWith(href);

  async function remove(id: string) {
    if (!window.confirm(m.common.confirmDelete)) return;
    await api.deleteConversation(id);
    await refreshConversations();
    if (pathname === `/chat/${id}`) router.push("/");
  }

  return (
    <nav className="flex h-full flex-col gap-4 p-3" aria-label="EZO">
      <Link href="/" onClick={onNavigate} className="flex items-center gap-2.5 px-2 pt-1">
        <EzoOrb size={28} />
        <span className="text-lg font-semibold tracking-[0.2em]">EZO</span>
      </Link>

      <Link
        href="/"
        onClick={onNavigate}
        className="flex h-10 items-center gap-2 rounded-xl border border-line bg-surface px-3 text-sm font-medium transition-colors hover:border-line-strong"
        data-testid="new-chat"
      >
        <Plus size={16} className="text-accent" />
        {m.common.newChat}
      </Link>

      <ul className="flex flex-col gap-0.5">
        {NAV_ORDER.map((key) => {
          const meta = MODULE_META[key];
          const Icon = meta.icon;
          const active = isActive(meta.href);
          return (
            <li key={key}>
              <Link
                href={meta.href}
                onClick={onNavigate}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex h-9 items-center gap-3 rounded-lg px-2.5 text-sm transition-colors",
                  active ? "bg-surface-2 text-ink" : "text-ink-muted hover:bg-surface-2/60 hover:text-ink",
                )}
              >
                <Icon size={17} className={active ? "text-accent" : undefined} />
                <span className="flex-1">{m.nav[key]}</span>
                {meta.milestone > 1 ? (
                  <span className="rounded-full border border-line px-1.5 text-[10px] text-ink-faint">
                    M{meta.milestone}
                  </span>
                ) : null}
              </Link>
            </li>
          );
        })}
      </ul>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <p className="px-2.5 pb-1.5 text-xs font-medium uppercase tracking-wider text-ink-faint">{m.common.recent}</p>
        {conversations.length === 0 ? (
          <p className="px-2.5 text-sm text-ink-faint">{m.common.noConversations}</p>
        ) : (
          <ul className="flex flex-col gap-0.5" data-testid="conversation-list">
            {conversations.map((conversation) => {
              const href = `/chat/${conversation.id}`;
              const active = pathname === href;
              return (
                <li key={conversation.id} className="group relative">
                  <Link
                    href={href}
                    onClick={onNavigate}
                    className={cn(
                      "block truncate rounded-lg py-1.5 pl-2.5 pr-8 text-sm transition-colors",
                      active ? "bg-surface-2 text-ink" : "text-ink-muted hover:bg-surface-2/60 hover:text-ink",
                    )}
                    title={conversation.title}
                  >
                    {conversation.title}
                  </Link>
                  <button
                    type="button"
                    onClick={() => void remove(conversation.id)}
                    aria-label={`${m.common.delete}: ${conversation.title}`}
                    className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-1 text-ink-faint opacity-0 transition-opacity hover:text-danger focus:opacity-100 group-hover:opacity-100"
                  >
                    <Trash2 size={14} />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <p className="px-2.5 text-xs leading-relaxed text-ink-faint">{m.product.tagline}</p>
    </nav>
  );
}
