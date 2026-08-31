export type ApiEnvelope<T> = { code: number; data: T; message: string };

const TOKEN_KEY = "quiz_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
  document.cookie = `quiz_auth=1; path=/; max-age=${60 * 60 * 24 * 7}; SameSite=Lax`;
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
  document.cookie = "quiz_auth=; path=/; max-age=0";
}

export async function downloadAuth(path: string, filename: string) {
  const token = getToken();
  const res = await fetch(path.startsWith("/api") ? path : `/api${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error("导出失败");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function messageFromResponse(status: number, text: string): string {
  const trimmed = text.trim();
  if (trimmed) {
    try {
      const json = JSON.parse(trimmed) as Partial<ApiEnvelope<unknown>> & { detail?: unknown };
      if (typeof json.message === "string" && json.message.trim()) return json.message;
      if (typeof json.detail === "string" && json.detail.trim()) return json.detail;
    } catch {
      /* plaintext / HTML / proxy 500 */
    }
  }
  if (status >= 500 || /^internal server error$/i.test(trimmed) || trimmed.startsWith("<")) {
    return "服务器繁忙，请稍后重试";
  }
  if (!trimmed) return "请求失败";
  return trimmed.length > 160 ? "请求失败" : trimmed;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(path.startsWith("/api") ? path : `/api${path}`, {
    cache: "no-store",
    ...init,
    headers,
  });
  const text = await res.text();
  let json: ApiEnvelope<T> | null = null;
  if (text.trim()) {
    try {
      json = JSON.parse(text) as ApiEnvelope<T>;
    } catch {
      throw new Error(messageFromResponse(res.status, text));
    }
  }
  if (!json) {
    throw new Error(messageFromResponse(res.status, text));
  }
  if (!res.ok || json.code !== 0) {
    throw new Error(json.message || messageFromResponse(res.status, text));
  }
  return json.data;
}
