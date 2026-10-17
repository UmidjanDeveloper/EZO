import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import { useId } from "react";
import { cn } from "./cn";

const control =
  "w-full rounded-xl border border-line bg-surface-2 px-3 py-2 text-sm text-ink placeholder:text-ink-faint " +
  "focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/25";

interface FieldShellProps {
  label: string;
  hint?: ReactNode;
  children: (id: string) => ReactNode;
}

function FieldShell({ label, hint, children }: FieldShellProps) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-ink">
        {label}
      </label>
      {children(id)}
      {hint ? <p className="text-xs text-ink-muted">{hint}</p> : null}
    </div>
  );
}

export function TextField({
  label,
  hint,
  className,
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: ReactNode }) {
  return (
    <FieldShell label={label} hint={hint}>
      {(id) => <input id={id} className={cn(control, "h-10", className)} {...rest} />}
    </FieldShell>
  );
}

export function TextAreaField({
  label,
  hint,
  className,
  ...rest
}: TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string; hint?: ReactNode }) {
  return (
    <FieldShell label={label} hint={hint}>
      {(id) => <textarea id={id} className={cn(control, "min-h-20 resize-y", className)} {...rest} />}
    </FieldShell>
  );
}

export function SelectField({
  label,
  hint,
  className,
  children,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement> & { label: string; hint?: ReactNode }) {
  return (
    <FieldShell label={label} hint={hint}>
      {(id) => (
        <select id={id} className={cn(control, "h-10", className)} {...rest}>
          {children}
        </select>
      )}
    </FieldShell>
  );
}
