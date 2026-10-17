import { notFound } from "next/navigation";
import { ComingSoonPage } from "@/components/pages/ComingSoonPage";
import { COMING_SOON, type ComingSoonKey } from "@/lib/modules";

export function generateStaticParams() {
  return COMING_SOON.map((module) => ({ module }));
}

export const dynamicParams = false;

export default async function Page({ params }: { params: Promise<{ module: string }> }) {
  const { module } = await params;
  if (!(COMING_SOON as readonly string[]).includes(module)) notFound();
  return <ComingSoonPage module={module as ComingSoonKey} />;
}
