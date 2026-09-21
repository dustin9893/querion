/**
 * Staff API calls the panel makes on its own (login, refresh, list assistants). The chat itself
 * goes through `staffTransport` from the web app, so the panel and the portal speak to the same
 * endpoints. Requests come from the extension origin with `host_permissions`, so no CORS setup is
 * needed on the API.
 */
import { getSession, setSession, tokenExpiry, type Session } from "./storage";

export interface StaffApp {
  id: string;
  name: string;
  description: string | null;
  logo_url: string | null;
  workspace_id: string;
  share_scope: "unit" | "bank";
  own_unit: boolean;
  suggestions: string[];
  greeting: string | null;
  extension_enabled: boolean;
  extension_hosts: string[];
  primary_color: string | null;
}
export interface AppGroup { workspace_name: string; apps: StaffApp[] }

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function readError(r: Response, fallback: string): Promise<string> {
  try { const j = await r.json(); return typeof j.detail === "string" ? j.detail : fallback; } catch { return fallback; }
}

export async function login(apiBase: string, email: string, password: string): Promise<Session> {
  const r = await fetch(`${apiBase}/v1/staff/login`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    // the surface is stamped into the token: the server, not this code, decides what it may list
    body: JSON.stringify({ email, password, client: "extension" }),
  });
  if (!r.ok) throw new ApiError(r.status, await readError(r, "Đăng nhập thất bại"));
  const j = await r.json();
  const session: Session = { access: j.access_token, refresh: j.refresh_token, employee: j.employee };
  await setSession(session);
  return session;
}

/** Refresh when the access token is gone or about to expire; drop the session when refresh fails. */
export async function ensureFreshToken(apiBase: string): Promise<Session | null> {
  const session = await getSession();
  if (!session) return null;
  if (tokenExpiry(session.access) - Date.now() > 2 * 60_000) return session;
  const r = await fetch(`${apiBase}/v1/staff/refresh`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh_token: session.refresh }),
  });
  if (!r.ok) { await setSession(null); return null; }
  const j = await r.json();
  const next = { ...session, access: j.access_token };
  await setSession(next);
  return next;
}

export async function listApps(apiBase: string, token: string): Promise<AppGroup[]> {
  const r = await fetch(`${apiBase}/v1/staff/apps`, { headers: { Authorization: `Bearer ${token}` } });
  if (!r.ok) throw new ApiError(r.status, await readError(r, "Không tải được danh sách trợ lý"));
  return r.json();
}

export async function logout() { await setSession(null); }
