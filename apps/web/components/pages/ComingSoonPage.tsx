"use client";

import { Badge, buttonClass, Card } from "@ezo/ui";
import { Check } from "lucide-react";
import Link from "next/link";
import { useI18n } from "@/lib/i18n/context";
import { MODULE_META, type ComingSoonKey } from "@/lib/modules";
import { PageFrame } from "./PageFrame";

export function ComingSoonPage({ module }: { module: ComingSoonKey }) {
  const { m, f } = useI18n();
  const meta = MODULE_META[module];
  const Icon = meta.icon;
  const texts = m.modules[module];
  return (
    <PageFrame title={texts.title}>
      <Card className="flex flex-col gap-5 p-8" data-testid="coming-soon">
        <div className="flex items-center gap-3">
          <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-accent/10 text-accent">
            <Icon size={24} />
          </span>
          <div>
            <Badge tone="warning">{m.modules.comingSoon}</Badge>
            <p className="mt-1 text-sm text-ink-muted">{f(m.modules.milestone, { n: meta.milestone })}</p>
          </div>
        </div>
        <div>
          <h2 className="mb-2 text-sm font-medium">{m.modules.whatsPlanned}</h2>
          <ul className="flex flex-col gap-1.5 text-sm text-ink-muted">
            {texts.features.map((feature) => (
              <li key={feature} className="flex items-center gap-2">
                <Check size={14} className="text-ink-faint" /> {feature}
              </li>
            ))}
          </ul>
        </div>
        <p className="text-sm text-ink-muted">{m.modules.meanwhile}</p>
        <div>
          <Link href="/" className={buttonClass({ variant: "primary" })}>
            {m.modules.openChat}
          </Link>
        </div>
      </Card>
    </PageFrame>
  );
}
