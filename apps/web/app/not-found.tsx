import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
      <p className="text-5xl font-semibold tracking-[0.3em] text-ink-faint">404</p>
      <Link href="/" className="text-sm text-accent underline underline-offset-4">
        EZO
      </Link>
    </div>
  );
}
