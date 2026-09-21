/**
 * Everything the extension remembers lives in chrome.storage — extension-private, so no web page
 * (not even the intranet page the bubble sits on) can read the staff token.
 *
 *   managed  → pushed by IT through Chrome Enterprise policy (apiBase, brandName, disabledHosts)
 *   local    → session, last assistant, bubble position per site, options override
 */
export interface ManagedConfig { apiBase?: string; brandName?: string; disabledHosts?: string[] }
export interface Session {
  access: string;
  refresh: string;
  employee: { id: string; name: string; employee_code?: string | null; position?: string | null; branch?: string | null; workspace_name?: string | null };
}
export interface Config { apiBase: string; webBase: string; brandName: string; managed: boolean; disabledHosts: string[] }

const DEFAULT_API = (import.meta.env.VITE_DEFAULT_API_BASE as string) || "http://localhost:8000";

export async function loadConfig(): Promise<Config> {
  let managed: ManagedConfig = {};
  try { managed = (await chrome.storage.managed.get(null)) as ManagedConfig; } catch { /* no policy */ }
  const local = (await chrome.storage.local.get("options")) as { options?: { apiBase?: string } };
  const apiBase = (managed.apiBase || local.options?.apiBase || DEFAULT_API).replace(/\/+$/, "");
  return {
    apiBase,
    // locally the web app is on :3000; behind Caddy web and API share one origin
    webBase: apiBase.replace(/:8000$/, ":3000"),
    brandName: managed.brandName || "MSB Knowledge Assistant",
    managed: !!managed.apiBase,
    disabledHosts: managed.disabledHosts || [],
  };
}

export async function saveOptions(options: { apiBase?: string }) {
  await chrome.storage.local.set({ options });
}

export async function getSession(): Promise<Session | null> {
  const r = (await chrome.storage.local.get("session")) as { session?: Session };
  return r.session || null;
}
export async function setSession(session: Session | null) {
  if (session) await chrome.storage.local.set({ session });
  else await chrome.storage.local.remove("session");
}

export async function getLastAppId(): Promise<string | null> {
  const r = (await chrome.storage.local.get("lastAppId")) as { lastAppId?: string };
  return r.lastAppId || null;
}
export async function setLastAppId(id: string) { await chrome.storage.local.set({ lastAppId: id }); }

export interface Pos { x: number; y: number }
export async function getPos(origin: string): Promise<Pos | null> {
  const key = `pos:${origin}`;
  const r = (await chrome.storage.local.get(key)) as Record<string, Pos>;
  return r[key] || null;
}
export async function setPos(origin: string, pos: Pos) { await chrome.storage.local.set({ [`pos:${origin}`]: pos }); }

/** exp claim of a JWT in ms, or 0 when unreadable. */
export function tokenExpiry(token: string | null | undefined): number {
  try {
    const payload = JSON.parse(atob((token || "").split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    return typeof payload.exp === "number" ? payload.exp * 1000 : 0;
  } catch { return 0; }
}
