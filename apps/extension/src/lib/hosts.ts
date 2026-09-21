/** Mirror of `app/services/extension.py:host_matches` — keep the two in step. */
export function hostMatches(pattern: string, host: string): boolean {
  pattern = (pattern || "").toLowerCase();
  host = (host || "").toLowerCase();
  if (!pattern || !host) return false;
  const [pHost, pPort] = splitPort(pattern);
  const [hHost, hPort] = splitPort(host);
  if (pPort && pPort !== hPort) return false;
  if (pHost.startsWith("*.")) return hHost.endsWith(pHost.slice(1)) && hHost !== pHost.slice(2);
  return pHost === hHost;
}

function splitPort(value: string): [string, string] {
  const i = value.indexOf(":");
  return i === -1 ? [value, ""] : [value.slice(0, i), value.slice(i + 1)];
}

export function anyHostMatches(patterns: string[] | undefined, host: string): boolean {
  return (patterns || []).some((p) => hostMatches(p, host));
}
