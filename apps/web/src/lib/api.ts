const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Default timeout for API calls (ms) */
const API_TIMEOUT = 8000;

type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
  /** Override default timeout (ms). Set to 0 for no timeout. */
  timeout?: number;
};

// In-memory token storage (more secure than localStorage for tokens)
let accessToken: string | null = null;
let activeWorkspaceId: string | null = null;

/** Turn an API-relative asset path (e.g. an assistant's `logo_url`) into a URL the browser can load. */
export function apiAssetUrl(path: string | null | undefined): string | null {
  if (!path) return null;
  return /^https?:\/\//.test(path) ? path : `${API_BASE_URL}${path}`;
}

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

export function setActiveWorkspaceId(id: string | null) {
  activeWorkspaceId = id;
}

export function getActiveWorkspaceId(): string | null {
  return activeWorkspaceId;
}

/** FastAPI returns `detail` as a string, or as a list of validation errors (422). */
function errorMessage(error: any, status: number): string {
  const d = error?.detail;
  if (typeof d === "string" && d) return d;
  if (Array.isArray(d) && d.length) {
    const first = d[0] || {};
    const loc = Array.isArray(first.loc) ? first.loc.slice(1).join(".") : "";
    if (loc === "X-Workspace-Id") return "Chưa chọn đơn vị làm việc. Hãy chọn đơn vị ở thanh bên trái.";
    return loc ? `${loc}: ${first.msg}` : first.msg || `API error: ${status}`;
  }
  return `API error: ${status}`;
}

/**
 * Base API client wrapping fetch with JSON defaults + auto auth headers + timeout.
 */
export async function apiFetch<T = unknown>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { body, headers, timeout = API_TIMEOUT, ...rest } = options;

  const authHeaders: Record<string, string> = {};
  if (accessToken) {
    authHeaders["Authorization"] = `Bearer ${accessToken}`;
  }
  if (activeWorkspaceId) {
    authHeaders["X-Workspace-Id"] = activeWorkspaceId;
  }

  // AbortController for timeout
  const controller = new AbortController();
  let timerId: ReturnType<typeof setTimeout> | undefined;
  if (timeout > 0) {
    timerId = setTimeout(() => controller.abort(), timeout);
  }

  try {
    const res = await fetch(`${API_BASE_URL}${path}`, {
      headers: {
        "Content-Type": "application/json",
        ...authHeaders,
        ...headers,
      },
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
      ...rest,
    });

    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(errorMessage(error, res.status));
    }

    return res.json() as Promise<T>;
  } catch (err: any) {
    if (err.name === "AbortError") {
      throw new Error("Request timed out");
    }
    throw err;
  } finally {
    if (timerId) clearTimeout(timerId);
  }
}

/**
 * Convenience methods
 */
export const api = {
  get: <T = unknown>(path: string, opts?: RequestOptions) =>
    apiFetch<T>(path, { method: "GET", ...opts }),

  post: <T = unknown>(path: string, body?: unknown, opts?: RequestOptions) =>
    apiFetch<T>(path, { method: "POST", body, ...opts }),

  patch: <T = unknown>(path: string, body?: unknown, opts?: RequestOptions) =>
    apiFetch<T>(path, { method: "PATCH", body, ...opts }),

  delete: <T = unknown>(path: string, opts?: RequestOptions) =>
    apiFetch<T>(path, { method: "DELETE", ...opts }),

  /** Upload a file via multipart/form-data. */
  upload: async <T = unknown>(path: string, formData: FormData, opts?: RequestOptions): Promise<T> => {
    const { headers, timeout = 60000 } = opts || {};

    const authHeaders: Record<string, string> = {};
    if (accessToken) authHeaders["Authorization"] = `Bearer ${accessToken}`;
    if (activeWorkspaceId) authHeaders["X-Workspace-Id"] = activeWorkspaceId;

    const controller = new AbortController();
    let timerId: ReturnType<typeof setTimeout> | undefined;
    if (timeout > 0) timerId = setTimeout(() => controller.abort(), timeout);

    try {
      const res = await fetch(`${API_BASE_URL}${path}`, {
        method: "POST",
        headers: { ...authHeaders, ...(headers as Record<string, string>) },
        body: formData as BodyInit,
        signal: controller.signal,
      });

      if (!res.ok) {
        const error = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(errorMessage(error, res.status));
      }

      return res.json() as Promise<T>;
    } catch (err: any) {
      if (err.name === "AbortError") throw new Error("Upload timed out");
      throw err;
    } finally {
      if (timerId) clearTimeout(timerId);
    }
  },
};
