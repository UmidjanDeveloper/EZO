"use client";

import type { KnowledgeStatus } from "@ezo/shared";
import { Badge } from "@ezo/ui";
import { Loader2 } from "lucide-react";
import { useI18n } from "@/lib/i18n/context";

const TONES = {
  queued: "neutral",
  processing: "accent",
  indexed: "success",
  partial: "warning",
  needs_ocr: "warning",
  failed: "danger",
} as const;

export function StatusBadge({ status }: { status: KnowledgeStatus }) {
  const { m } = useI18n();
  return (
    <Badge tone={TONES[status]} data-testid="knowledge-status" data-status={status}>
      {status === "processing" || status === "queued" ? <Loader2 size={11} className="animate-spin" /> : null}
      {m.knowledge.status[status]}
    </Badge>
  );
}
