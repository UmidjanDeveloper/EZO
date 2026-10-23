"use client";

import { cn } from "@ezo/ui";
import {
  Award,
  Bot,
  Brain,
  ChevronDown,
  ChevronRight,
  FileSpreadsheet,
  FileStack,
  FolderKanban,
  GraduationCap,
  Languages,
  Layers,
  PanelLeftClose,
  Plus,
  Presentation,
  Settings,
  ShieldCheck,
  Terminal,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { useApp } from "@/lib/app-state";
import { useI18n } from "@/lib/i18n/context";
import { EzoRobot } from "../robot/EzoRobot";

interface NavItem {
  href: string;
  label: string;
  icon: typeof FileStack;
  category: "core" | "learn" | "work" | "intelligence" | "system";
  badge?: string;
}

/** EZO OS Dock & Conversation History: the primary operating system navigation. */
export function HistoryPanel({ onNavigate, onClose }: { onNavigate?: () => void; onClose?: () => void }) {
  const { m } = useI18n();
  const pathname = usePathname();
  const router = useRouter();
  const { conversations, refreshConversations, status } = useApp();
  const [appsExpanded, setAppsExpanded] = useState(true);

  async function remove(id: string) {
    if (!window.confirm(m.common.confirmDelete)) return;
    await api.deleteConversation(id);
    await refreshConversations();
    if (pathname === `/chat/${id}`) router.push("/");
  }

  const allApps: NavItem[] = [
    { href: "/student", label: m.nav.student ?? "EZO Student", icon: FileStack, category: "learn" as const, badge: "V4" },
    { href: "/ielts", label: m.nav.ielts, icon: Award, category: "learn" as const, badge: "2.0" },
    { href: "/jarvis", label: m.nav.jarvis ?? "JARVIS Rejimi", icon: Terminal, category: "intelligence" as const, badge: "OS" },
    { href: "/presentations", label: m.nav.presentations, icon: Presentation, category: "work" as const },
    { href: "/office", label: m.nav.office, icon: FileSpreadsheet, category: "work" as const },
    { href: "/language", label: m.nav.language, icon: GraduationCap, category: "learn" as const },
    { href: "/translate", label: m.nav.translation, icon: Languages, category: "learn" as const },
    { href: "/artifacts", label: m.nav.artifacts, icon: Layers, category: "core" as const },
    { href: "/knowledge", label: m.nav.knowledge, icon: FileStack, category: "intelligence" as const },
    { href: "/memory", label: m.nav.memory, icon: Brain, category: "intelligence" as const },
    { href: "/projects", label: m.nav.projects, icon: FolderKanban, category: "intelligence" as const },
    { href: "/admin", label: m.nav.admin, icon: ShieldCheck, category: "system" as const, badge: "RBAC" },
    { href: "/settings", label: m.nav.settings, icon: Settings, category: "system" as const },
  ].filter(
    (item) =>
      status?.deployment_profile !== "free-beta" ||
      !["/student", "/presentations", "/language", "/translate", "/knowledge", "/jarvis"].includes(item.href)
  );

  return (
    <nav className="flex h-full flex-col gap-2.5 p-3 text-ink select-none overflow-hidden" aria-label={m.nav.history}>
      {/* Header & Brand */}
      <div className="flex items-center justify-between px-1.5 pt-1">
        <Link href="/" onClick={onNavigate} className="flex items-center gap-2.5 transition-opacity hover:opacity-90">
          <EzoRobot size={32} showHalo={false} />
          <div className="flex flex-col">
            <span className="text-sm font-bold tracking-[0.22em] text-ink">EZO OS</span>
            <span className="text-[10px] font-mono text-accent">Universal AI Robot</span>
          </div>
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

      {/* Primary Action: New Chat */}
      <Link
        href="/"
        onClick={onNavigate}
        className="flex h-10 items-center gap-2.5 rounded-xl border border-accent/40 bg-accent/10 px-3.5 text-sm font-semibold text-accent transition-all hover:bg-accent/15 hover:border-accent"
        data-testid="new-chat"
      >
        <Plus size={16} className="text-accent shrink-0" />
        <span>{m.common.newChat}</span>
      </Link>

      {/* Collapsible EZO OS Apps Dock */}
      <div className="rounded-xl border border-line bg-surface/70 backdrop-blur-sm p-1.5">
        <button
          type="button"
          onClick={() => setAppsExpanded(!appsExpanded)}
          className="flex w-full items-center justify-between px-2 py-1 text-xs font-semibold uppercase tracking-wider text-ink-muted hover:text-ink"
        >
          <span className="flex items-center gap-1.5">
            <Bot size={13} className="text-accent" />
            EZO Ilovalar
          </span>
          {appsExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>

        {appsExpanded && (
          <div className="mt-1 grid max-h-[195px] overflow-y-auto pr-0.5 gap-0.5 scrollbar-thin">
            {allApps.map(({ href, label, icon: Icon, badge }) => {
              const active = pathname.startsWith(href);
              return (
                <Link
                  key={href}
                  href={href}
                  onClick={onNavigate}
                  aria-label={label}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex items-center justify-between rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors",
                    active
                      ? "bg-accent/15 text-accent font-semibold"
                      : "text-ink-muted hover:bg-surface-2 hover:text-ink"
                  )}
                >
                  <span className="flex items-center gap-2 truncate">
                    <Icon size={14} className={cn(active ? "text-accent" : "text-ink-faint shrink-0")} />
                    <span className="truncate">{label}</span>
                  </span>
                  {badge && (
                    <span className="rounded bg-surface-3 px-1 py-0.2 text-[9px] font-mono text-ink-faint uppercase">
                      {badge}
                    </span>
                  )}
                </Link>
              );
            })}
          </div>
        )}
      </div>

      {/* Conversations History List */}
      <div className="min-h-0 flex-1 overflow-y-auto px-0.5">
        <p className="px-2 pb-1.5 text-xs font-medium uppercase tracking-wider text-ink-faint">{m.nav.history}</p>
        {conversations.length === 0 ? (
          <p className="px-2 text-xs text-ink-faint">{m.common.noConversations}</p>
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
                      "block truncate rounded-lg py-1.5 pl-2.5 pr-8 text-xs transition-colors",
                      active ? "bg-surface-2 text-ink font-medium" : "text-ink-muted hover:bg-surface-2/60 hover:text-ink"
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
                    <Trash2 size={13} />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Footer System Status Bar */}
      <div className="flex items-center justify-between border-t border-line/70 pt-2 px-1 text-[11px] text-ink-faint">
        <div className="flex items-center gap-1.5 truncate">
          <span className="h-2 w-2 rounded-full bg-emerald-500 shrink-0" />
          <span className="truncate">{status?.environment === "production" ? "Prod" : "Dev Local"}</span>
        </div>
        <Link
          href="/settings"
          onClick={onNavigate}
          className="hover:text-ink text-[11px] transition-colors"
        >
          v{status?.version ?? "0.2.0"}
        </Link>
      </div>
    </nav>
  );
}

