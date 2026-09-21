/** File formats a knowledge base accepts — the one place the web encodes them. */
export const KB_EXTENSIONS = ["pdf", "docx", "txt", "xlsx"] as const;

/** Value for the upload input's `accept` attribute, e.g. ".pdf,.docx,.txt,.xlsx". */
export const KB_ACCEPT = KB_EXTENSIONS.map((ext) => `.${ext}`).join(",");

const KB_EXT_RE = new RegExp(`\\.(${KB_EXTENSIONS.join("|")})$`, "i");

/** "Biểu phí 2026.pdf" -> "Biểu phí 2026"; anything else is returned unchanged. */
export function stripDocExt(filename: string): string {
  return filename.replace(KB_EXT_RE, "");
}
