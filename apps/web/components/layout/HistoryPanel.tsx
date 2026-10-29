"use client";

import { cn } from "@ezo/ui";
import {
  Award,
  Bot,
  Brain,
  FileSpreadsheet,
  FileStack,
  FolderKanban,
  GraduationCap,
  Languages,
  Layers,
  PanelLeftClose,
  Plus,
  Presentation,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useApp } from "@/lib/app-state";
import { useI18n } from "@/lib/i18n/context";
import { EnergyMark } from "../robot/EnergyMark";

/** Conversation history: the primary navigation for EZO OS. */
export function HistoryPanel({ onNavigate, onClose }: { onNavigate?: () => void; onClose?: () => void }) {
  const { m } = useI18n();
  const pathname = usePathname();
  const router = useRouter();
  const { conversations, refreshConversations, status } = useApp();

  async function remove(id: string) {
    if (!window.confirm(m.common.confirmDelete)) return;
    await api.deleteConversation(id);
    await refreshConversations();
    if (pathname === `/chat/${id}`) router.push("/");
  }

  const footer = [
    { href: "/artifacts", label: m.nav.artifacts, icon: Layers },
    { href: "/student", label: "Student", icon: FileStack },
    { href: "/presentations", label: m.nav.presentations, icon: Presentation },
    { href: "/office", label: m.nav.office, icon: FileSpreadsheet },
    { href: "/ielts", label: m.nav.ielts, icon: Award },
    { href: "/language", label: m.nav.language, icon: GraduationCap },
    { href: "/translate", label: m.nav.translation, icon: Languages },
    { href: "/knowledge", label: m.nav.knowledge, icon: FileStack },
    { href: "/memory", label: m.nav.memory, icon: Brain },
    { href: "/projects", label: m.nav.projects, icon: FolderKanban },
    { href: "/jarvis", label: m.nav.jarvis ?? "JARVIS", icon: Bot },
    { href: "/admin", label: m.nav.admin, icon: ShieldCheck },
  ].filter(
    (item) =>
      status?.deployment_profile !== "free-beta" ||
      !["/student", "/presentations", "/language", "/translate", "/knowledge", "/jarvis", "/admin"].includes(item.href)
  );

  return (
    <nav className="flex h-full flex-col gap-3 p-3" aria-label={m.nav.history}>
      <div className="flex items-center justify-between px-1">
        <Link href="/" onClick={onNavigate} className="flex items-center gap-2">
          <EnergyMark size={30} />
          <span className="text-base font-semibold tracking-[0.25em]">EZO</span>
        </Link>
        {onClose ? (
          <button
            type="button"
            onClick={onClose}
            aria-label={m.nav.closeHistory}
            title={m.nav.closeHistory}
            className="rounded-lg p-1.5 text-ink-faint transition-colors hover:bg-surface-2 hover:text-ink"
          >
            <PanelLeftClose size={18} />
          </button>
        ) : null}
      </div>

      <Link
        href="/"
        onClick={onNavigate}
        className="flex h-10 items-center gap-2 rounded-xl border border-line bg-surface px-3 text-sm font-medium transition-colors hover:border-accent/50"
        data-testid="new-chat"
      >
        <Plus size={16} className="text-accent" />
        {m.common.newChat}
      </Link>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <p className="px-2 pb-1.5 text-xs font-medium uppercase tracking-wider text-ink-faint">{m.nav.history}</p>
        {conversations.length === 0 ? (
          <p className="px-2 text-sm text-ink-faint">{m.common.noConversations}</p>
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
                      "block truncate rounded-lg py-2 pl-2.5 pr-8 text-sm transition-colors",
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

      <div className="flex flex-wrap items-center justify-around gap-0.5 border-t border-line pt-2">
        {footer.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            aria-label={label}
            title={label}
            aria-current={pathname.startsWith(href) ? "page" : undefined}
            className={cn(
              "rounded-lg p-2 transition-colors hover:bg-surface-2 hover:text-ink",
              pathname.startsWith(href) ? "text-accent" : "text-ink-faint",
            )}
          >
            <Icon size={18} />
          </Link>
        ))}
      </div>
    </nav>
  );
}

