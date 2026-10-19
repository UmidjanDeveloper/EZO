import type { Metadata, Viewport } from "next";
import { headers } from "next/headers";
import type { ReactNode } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { themeInitScript } from "@/lib/theme";
import { Providers } from "./providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "EZO",
  description: "EZO — Sen bilan o‘sadigan shaxsiy sun’iy intellekt.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f6f5f1" },
    { media: "(prefers-color-scheme: dark)", color: "#0a0b0f" },
  ],
};

export default async function RootLayout({ children }: { children: ReactNode }) {
  // Per-request nonce from proxy.ts: only scripts carrying it may run (CSP).
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    <html lang="uz" suppressHydrationWarning>
      <head>
        <script nonce={nonce} dangerouslySetInnerHTML={{ __html: themeInitScript }} />
        {/* Runtime API URL (no rebuild needed to point the web app at another API). */}
        {/* eslint-disable-next-line @next/next/no-sync-scripts */}
        <script nonce={nonce} src="/ezo-config" />
      </head>
      <body>
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
