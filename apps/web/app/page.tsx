import { ChatView } from "@/components/chat/ChatView";

export default async function HomePage({ searchParams }: { searchParams: Promise<{ project?: string }> }) {
  const { project } = await searchParams;
  return <ChatView key={project ?? "home"} projectId={project} />;
}
