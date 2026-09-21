import { NextResponse, type NextRequest } from "next/server";

/**
 * Per-assistant CSP for the embeddable widget page.
 *
 * /embed/<appId> may only be framed by the origins the admin allow-listed for that
 * assistant (GET /v1/public/assistants/<id>/frame-ancestors). Unknown / disabled
 * assistants get `frame-ancestors 'none'` — fail closed. Every other route gets
 * X-Frame-Options: DENY from next.config.ts.
 */
const API_BASE = process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const TTL_MS = 30_000;
const cache = new Map<string, { exp: number; origins: string[] | null }>();

async function allowedOrigins(appId: string): Promise<string[] | null> {
  const hit = cache.get(appId);
  const now = Date.now();
  if (hit && hit.exp > now) return hit.origins;
  let origins: string[] | null = null;
  try {
    const r = await fetch(`${API_BASE}/v1/public/assistants/${encodeURIComponent(appId)}/frame-ancestors`, { cache: "no-store" });
    if (r.ok) {
      const j = await r.json();
      origins = Array.isArray(j.allowed_origins) ? j.allowed_origins.filter((o: unknown) => typeof o === "string" && /^https?:\/\/[^\s'";]+$/.test(o)) : [];
    }
  } catch {
    origins = null; // API unreachable → deny framing
  }
  cache.set(appId, { exp: now + TTL_MS, origins });
  return origins;
}

export async function proxy(req: NextRequest) {
  const m = req.nextUrl.pathname.match(/^\/embed\/([^/]+)/);
  const res = NextResponse.next();
  if (!m) return res;
  const origins = await allowedOrigins(decodeURIComponent(m[1]));
  const ancestors = origins && origins.length ? `'self' ${origins.join(" ")}` : "'self'";
  // 'self' keeps the admin "preview" iframe working; everything else must be allow-listed.
  res.headers.set("Content-Security-Policy", `frame-ancestors ${ancestors}`);
  res.headers.delete("X-Frame-Options");
  res.headers.set("X-Robots-Tag", "noindex");
  return res;
}

export const config = {
  matcher: ["/embed/:path*"],
};
