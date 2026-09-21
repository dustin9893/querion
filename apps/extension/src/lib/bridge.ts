/**
 * Message protocol between the content script (bubble on the page) and the panel (extension page
 * in the iframe). Both sides check the exact counterpart origin and window — never "*".
 */
export const PROTOCOL = "msbka-ext/1";

/** What the bubble knows about the page; the panel picks the default assistant from `host`. */
export interface PageContext {
  origin: string;      // https://bpm.msb.local:8443
  host: string;        // bpm.msb.local:8443 (matches `extension_hosts` rules)
  href: string;
  title: string;
  selection: string;   // trimmed, capped
}

export type ToPanel =
  | { type: "context"; context: PageContext }
  | { type: "visibility"; visible: boolean };

export type ToPage =
  | { type: "ready"; color: string; title: string }
  | { type: "close" }
  | { type: "unread"; count: number };

export const MAX_SELECTION = 2000;

/** The extension's own origin (chrome-extension://<id>) — what the page must address messages to. */
export function extensionOrigin(): string {
  return new URL(chrome.runtime.getURL("")).origin;
}
