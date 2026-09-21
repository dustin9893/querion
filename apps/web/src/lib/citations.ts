/** Shared helpers for rendering retrieval citations (staff portal, customer page, admin). */

import { stripDocExt } from "./kbFormats";

export interface Source {
  chunk_id: string;
  filename?: string;
  content?: string;
  content_preview?: string;
  score?: number;
  chunk_index?: number;
  document_id?: string;
  dataset_id?: string;
  doc_type?: string | null;
  version?: string | null;
  effective_from?: string | null;
  section?: string | null;
}

/** Pull the "[Điều 5. ...]" breadcrumb the chunker prefixes onto each chunk. */
export function sectionOf(src: Source): string | null {
  if (src.section) return src.section;
  const text = src.content || src.content_preview || "";
  const m = text.match(/^\[([^\]]{1,160})\]/);
  return m ? m[1] : null;
}

/** "Quy trình cấp tín dụng KHDN (EB) v3.2 · hiệu lực 01/03/2026 · Điều 5. Phê duyệt tín dụng" */
export function sourceLabel(src: Source): string {
  const bits: string[] = [];
  if (src.filename) bits.push(stripDocExt(src.filename));
  if (src.effective_from) bits.push(`hiệu lực ${src.effective_from}`);
  const sec = sectionOf(src);
  if (sec) bits.push(sec);
  return bits.join(" · ");
}

/** Body text of a chunk without the breadcrumb prefix, for tooltips / previews. */
export function sourceBody(src: Source, max = 400): string {
  const text = src.content || src.content_preview || "";
  return text.replace(/^\[[^\]]{1,160}\]\s*/, "").slice(0, max);
}
