import { apiUrl, storedToken } from "./api";

/** Student-specific client: private documents are never cached by this client. */
export async function studentRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = storedToken.get().trim();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${apiUrl()}/api/${path}`, { ...init, cache: "no-store", headers });
  // 204 (e.g. a confirmed delete) has no body to parse.
  const body = response.status === 204 ? "" : await response.text();
  const value = body ? JSON.parse(body) : undefined;
  if (!response.ok) throw new Error(value?.detail?.message ?? value?.error?.message ?? "So‘rov bajarilmadi. Qayta urinib ko‘ring.");
  return value;
}

/** Backend offsets count Unicode code points; JS string.length counts UTF-16 units. */
export function hasNextStudentPage(page: { offset: number; text: string; total_chars: number }): boolean {
  return page.offset + Array.from(page.text).length < page.total_chars;
}
