"use client";

import { Button, Card, Spinner, TextAreaField, TextField } from "@ezo/ui";
import { FolderKanban, Plus } from "lucide-react";
import Link from "next/link";
import { useCallback, useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n/context";
import { useApiData } from "@/lib/use-api-data";
import { PageFrame } from "./PageFrame";

export function ProjectsPage() {
  const { m, language } = useI18n();
  const { data: projects, error: loadError, reload } = useApiData(useCallback(() => api.listProjects(), []));
  const [actionError, setError] = useState<string | null>(null);
  const error = actionError ?? loadError?.message ?? null;
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    try {
      await api.createProject(name.trim(), description.trim());
      setName("");
      setDescription("");
      setError(null);
      reload();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <PageFrame title={m.projects.title} subtitle={m.projects.subtitle}>
      <Card className="mb-6">
        <form onSubmit={create} className="flex flex-col gap-3" data-testid="project-form">
          <TextField label={m.projects.name} value={name} onChange={(e) => setName(e.target.value)} maxLength={200} required />
          <TextAreaField
            label={m.projects.description}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            maxLength={4000}
            rows={2}
          />
          <div>
            <Button type="submit" variant="primary" icon={<Plus size={16} />} disabled={busy || !name.trim()}>
              {m.projects.create}
            </Button>
          </div>
        </form>
      </Card>

      {error ? <p className="mb-4 text-sm text-danger">{error}</p> : null}
      {projects === null && !error ? <Spinner label={m.common.loading} /> : null}
      {projects?.length === 0 ? <p className="text-sm text-ink-muted">{m.projects.empty}</p> : null}

      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2" data-testid="project-list">
        {projects?.map((project) => (
          <li key={project.id}>
            <Link
              href={`/projects/${project.id}`}
              className="flex h-full flex-col gap-2 rounded-2xl border border-line bg-surface p-4 transition-colors hover:border-accent/50"
            >
              <span className="flex items-center gap-2 font-medium">
                <FolderKanban size={16} className="text-accent" /> {project.name}
              </span>
              {project.description ? <span className="line-clamp-2 text-sm text-ink-muted">{project.description}</span> : null}
              <span className="mt-auto text-xs text-ink-faint">
                {new Date(project.updated_at).toLocaleDateString(language)}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </PageFrame>
  );
}
