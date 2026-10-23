/**
 * Search file NAMES inside folders the user explicitly allowed. File contents are
 * never read here, symlinks are never followed, and every result is re-checked to be
 * inside an allowed folder before it may be opened.
 */
import { lstat, readdir, realpath } from "node:fs/promises";
import path from "node:path";

export interface FileHit {
  path: string;
  name: string;
  folder: string;
  modified: number;
  size: number;
}

export const SEARCH_LIMITS = { maxDepth: 6, maxEntries: 20_000, maxResults: 20 } as const;
const SKIP_DIRS = new Set(["node_modules", ".git", "$recycle.bin", "appdata", "system volume information"]);

function tokens(query: string): string[] {
  return query
    .toLowerCase()
    .split(/[\s_\-.]+/)
    .filter((t) => t.length > 0);
}

/** True when `candidate` is one of `roots` or inside one (after resolving real paths). */
export async function isInsideAllowed(candidate: string, roots: readonly string[]): Promise<boolean> {
  let real: string;
  try {
    real = await realpath(candidate);
  } catch {
    return false;
  }
  for (const root of roots) {
    let realRoot: string;
    try {
      realRoot = await realpath(root);
    } catch {
      continue;
    }
    const relative = path.relative(realRoot, real);
    if (relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative))) return true;
  }
  return false;
}

export async function findFiles(query: string, roots: readonly string[]): Promise<FileHit[]> {
  const wanted = tokens(query);
  if (wanted.length === 0 || roots.length === 0) return [];
  const hits: FileHit[] = [];
  let seen = 0;

  async function walk(dir: string, depth: number, root: string): Promise<void> {
    if (depth > SEARCH_LIMITS.maxDepth || seen >= SEARCH_LIMITS.maxEntries) return;
    let entries;
    try {
      entries = await readdir(dir, { withFileTypes: true });
    } catch {
      return; // unreadable folder: skip, never escalate
    }
    for (const entry of entries) {
      if (++seen > SEARCH_LIMITS.maxEntries) return;
      if (entry.isSymbolicLink()) continue;
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (!SKIP_DIRS.has(entry.name.toLowerCase()) && !entry.name.startsWith(".")) {
          await walk(full, depth + 1, root);
        }
        continue;
      }
      if (!entry.isFile()) continue;
      const name = entry.name.toLowerCase();
      if (!wanted.every((t) => name.includes(t))) continue;
      try {
        const info = await lstat(full);
        hits.push({ path: full, name: entry.name, folder: root, modified: info.mtimeMs, size: info.size });
      } catch {
        // vanished between readdir and lstat
      }
    }
  }

  for (const root of roots) await walk(root, 0, root);
  return hits.sort((a, b) => b.modified - a.modified).slice(0, SEARCH_LIMITS.maxResults);
}
