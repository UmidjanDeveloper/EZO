import { cn } from "./cn";

export function Spinner({ className, label }: { className?: string; label?: string }) {
  return (
    <span role="status" className={cn("inline-flex items-center gap-2", className)}>
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-accent" />
      {label ? <span className="text-sm text-ink-muted">{label}</span> : <span className="sr-only">…</span>}
    </span>
  );
}
