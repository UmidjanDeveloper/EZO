"use client";

import type { Memory } from "@ezo/shared";
import { Button, buttonClass, Card, Spinner } from "@ezo/ui";
import { MessageSquarePlus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback } from "react";
import { api } from "@/lib/api";
import { useApp } from "@/lib/app-state";
import { useI18n } from "@/lib/i18n/context";
import { useApiData } from "@/lib/use-api-data";
import { MemoryList } from "./MemoryList";
import { PageFrame } from "./PageFrame";

export function ProjectDetailPage({ id }: { id: string }) {
  const { m } = useI18n();
  const router = useRouter();
  const { refreshConversations } = useApp();
  const fetchAll = useCallback(
    () => Promise.all([api.getProject(id), api.listConversations(id), api.listMemories({ projectId: id })]),
    [id],
  );
  const { data, error: loadError, reload } = useApiData(fetchAll);
  const [project, conversations, memories] = data ?? [null, [], []];
  const error = loadError ? (loadError.status === 404 ? m.projects.notFound : loadError.message) : null;

  async function remove() {
    if (!window.confirm(m.projects.deleteConfirm)) return;
    await api.deleteProject(id);
    await refreshConversations();
    router.push("/projects");
  }

  async function removeMemory(memory: Memory) {
    await api.deleteMemory(memory.id);
    reload();
  }

  if (error) return <PageFrame title={m.projects.title}><p className="text-danger">{error}</p></PageFrame>;
  if (!project) return <PageFrame title={m.projects.title}><Spinner label={m.common.loading} /></PageFrame>;

  return (
    <PageFrame
      title={project.name}
      subtitle={project.description || undefined}
      actions={
        <div className="flex gap-2">
          <Link href={`/?project=${project.id}`} className={buttonClass({ variant: "primary" })} data-testid="project-new-chat">
            <MessageSquarePlus size={16} /> {m.projects.newChat}
          </Link>
          <Button variant="danger" icon={<Trash2 size={16} />} onClick={() => void remove()}>
            {m.common.delete}
          </Button>
        </div>
      }
    >
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <h2 className="mb-3 font-medium">{m.projects.conversations}</h2>
          {conversations.length === 0 ? (
            <p className="text-sm text-ink-muted">{m.common.noConversations}</p>
          ) : (
            <ul className="flex flex-col gap-1">
              {conversations.map((conversation) => (
                <li key={conversation.id}>
                  <Link href={`/chat/${conversation.id}`} className="block truncate rounded-lg px-2 py-1.5 text-sm hover:bg-surface-2">
                    {conversation.title}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card>
          <h2 className="mb-3 font-medium">{m.projects.memories}</h2>
          {memories.length === 0 ? (
            <p className="text-sm text-ink-muted">{m.memory.empty}</p>
          ) : (
            <MemoryList memories={memories} onDelete={(memory) => void removeMemory(memory)} />
          )}
        </Card>
      </div>
    </PageFrame>
  );
}
