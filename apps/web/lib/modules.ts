import {
  AudioLines,
  Brain,
  Code2,
  FileText,
  FolderKanban,
  GraduationCap,
  ListChecks,
  MessageSquare,
  Palette,
  Settings,
  Telescope,
  type LucideIcon,
} from "lucide-react";
import type { Messages } from "./i18n/messages";

export type ModuleKey = keyof Messages["nav"] & keyof typeof MODULE_META;

interface ModuleMeta {
  href: string;
  icon: LucideIcon;
  /** Milestone that delivers the module; modules with milestone 1 are available now. */
  milestone: number;
}

export const MODULE_META = {
  chat: { href: "/", icon: MessageSquare, milestone: 1 },
  voice: { href: "/voice", icon: AudioLines, milestone: 7 },
  projects: { href: "/projects", icon: FolderKanban, milestone: 1 },
  learn: { href: "/learn", icon: GraduationCap, milestone: 3 },
  studio: { href: "/studio", icon: Palette, milestone: 4 },
  documents: { href: "/documents", icon: FileText, milestone: 4 },
  code: { href: "/code", icon: Code2, milestone: 6 },
  research: { href: "/research", icon: Telescope, milestone: 2 },
  memory: { href: "/memory", icon: Brain, milestone: 1 },
  tasks: { href: "/tasks", icon: ListChecks, milestone: 8 },
  settings: { href: "/settings", icon: Settings, milestone: 1 },
} satisfies Record<string, ModuleMeta>;

export const NAV_ORDER: ModuleKey[] = [
  "chat",
  "voice",
  "projects",
  "learn",
  "studio",
  "documents",
  "code",
  "research",
  "memory",
  "tasks",
  "settings",
];

/** Modules that are shown as "coming soon" pages in this milestone. */
export const COMING_SOON = ["voice", "learn", "studio", "documents", "code", "research", "tasks"] as const;
export type ComingSoonKey = (typeof COMING_SOON)[number];
