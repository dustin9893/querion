"use client";

import type { CSSProperties, ReactNode } from "react";

/**
 * Renders a `chart` fenced code block from an LLM answer as a small inline SVG
 * chart. Pure SVG + plain React — no chart library, no DOM measurement (this
 * also runs server-side via renderToStaticMarkup and inside the Chrome
 * extension, which shares this file through the `@` alias), no `window` or
 * `process` at module scope so it is safe in both the Next.js app and the
 * extension's Vite build.
 *
 * Expected JSON shape (see `parseSpec` for exact validation):
 *   { "loai": "cot" | "cot_ngang" | "duong" | "tron",
 *     "tieu_de"?: string, "don_vi"?: string,
 *     "nhan": string[], "chuoi": [{ "ten": string, "gia_tri": number[] }],
 *     "ghi_chu"?: string }
 */

const PALETTE = ["#1f3a5f", "#0f8b8d", "#d4a017", "#6b4ea1", "#64748b", "#2e8b57"];
const ACCENT = "var(--accent, #ee6d1f)";
const MAX_CATEGORIES = 12;
const MAX_SERIES = 4;
const VB_W = 600;

type ChartType = "cot" | "cot_ngang" | "duong" | "tron";

interface SeriesSpec {
  ten: string;
  gia_tri: number[];
}

interface ChartSpec {
  loai: ChartType;
  tieu_de?: string;
  don_vi?: string;
  nhan: string[];
  chuoi: SeriesSpec[];
  ghi_chu?: string;
}

interface Props {
  /** Already-parsed chart JSON. Ignored if `source` is given. */
  spec?: unknown;
  /** Raw text of the fenced code block (will be JSON.parse'd). */
  source?: string;
}

export default function ChartBlock({ spec, source }: Props) {
  const raw = source !== undefined ? tryParseJson(source) : { ok: true as const, value: spec };
  const parsed = raw.ok ? parseSpec(raw.value) : null;

  if (!parsed) {
    const rawText = source !== undefined ? source : safeStringify(spec);
    return (
      <div style={{ margin: "0.5em 0" }}>
        <div style={{ fontSize: "0.85em", opacity: 0.65, marginBottom: 4 }}>Không vẽ được biểu đồ</div>
        <pre
          style={{
            fontSize: "0.78em",
            padding: "8px 10px",
            borderRadius: 6,
            background: "rgba(128,128,128,0.12)",
            overflowX: "auto",
            margin: 0,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        >
          {rawText}
        </pre>
      </div>
    );
  }

  const label = describeSpec(parsed);
  const layout = buildLayout(parsed);

  return (
    <svg
      viewBox={`0 0 ${VB_W} ${layout.height}`}
      style={{ width: "100%", height: "auto", display: "block", margin: "0.5em 0" }}
      role="img"
      aria-label={label}
    >
      {layout.content}
    </svg>
  );
}

/* ---------------------------------------------------------------------- */
/* Parsing & validation                                                    */
/* ---------------------------------------------------------------------- */

function tryParseJson(text: string): { ok: true; value: unknown } | { ok: false } {
  try {
    return { ok: true, value: JSON.parse(text.trim()) };
  } catch {
    return { ok: false };
  }
}

function safeStringify(v: unknown): string {
  try {
    return JSON.stringify(v, null, 2) ?? String(v);
  } catch {
    return String(v);
  }
}

const CHART_TYPES: ChartType[] = ["cot", "cot_ngang", "duong", "tron"];

function parseSpec(value: unknown): ChartSpec | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const v = value as Record<string, unknown>;

  const loai = v.loai;
  if (typeof loai !== "string" || !CHART_TYPES.includes(loai as ChartType)) return null;

  if (!Array.isArray(v.nhan) || v.nhan.length === 0) return null;
  const nhan = v.nhan.slice(0, MAX_CATEGORIES).map((x) => (x === null || x === undefined ? "" : String(x)));
  if (nhan.every((n) => n === "")) return null;

  if (!Array.isArray(v.chuoi) || v.chuoi.length === 0) return null;
  const chuoiRaw = v.chuoi.slice(0, MAX_SERIES);
  const chuoi: SeriesSpec[] = [];
  for (let i = 0; i < chuoiRaw.length; i++) {
    const s = chuoiRaw[i];
    if (!s || typeof s !== "object" || Array.isArray(s)) continue;
    const sr = s as Record<string, unknown>;
    const ten = typeof sr.ten === "string" && sr.ten.trim() ? sr.ten : `Chuỗi ${i + 1}`;
    const valuesIn = Array.isArray(sr.gia_tri) ? sr.gia_tri : [];
    const gia_tri: number[] = [];
    for (let j = 0; j < nhan.length; j++) {
      const raw = valuesIn[j];
      const n = typeof raw === "number" ? raw : Number(raw);
      gia_tri.push(Number.isFinite(n) ? n : 0);
    }
    chuoi.push({ ten, gia_tri });
  }
  if (chuoi.length === 0) return null;

  const tieu_de = typeof v.tieu_de === "string" && v.tieu_de.trim() ? v.tieu_de : undefined;
  const don_vi = typeof v.don_vi === "string" && v.don_vi.trim() ? v.don_vi : undefined;
  const ghi_chu = typeof v.ghi_chu === "string" && v.ghi_chu.trim() ? v.ghi_chu : undefined;

  return { loai: loai as ChartType, tieu_de, don_vi, nhan, chuoi, ghi_chu };
}

function describeSpec(spec: ChartSpec): string {
  const kind =
    spec.loai === "cot" ? "Biểu đồ cột" : spec.loai === "cot_ngang" ? "Biểu đồ cột ngang" : spec.loai === "duong" ? "Biểu đồ đường" : "Biểu đồ tròn";
  const title = spec.tieu_de ? `: ${spec.tieu_de}` : "";
  const parts = [`${kind}${title}`, `${spec.nhan.length} danh mục`];
  if (spec.loai !== "tron") parts.push(`${spec.chuoi.length} chuỗi dữ liệu`);
  if (spec.don_vi) parts.push(`đơn vị ${spec.don_vi}`);
  return parts.join(", ");
}

/* ---------------------------------------------------------------------- */
/* Formatting helpers                                                      */
/* ---------------------------------------------------------------------- */

/** Full value with Vietnamese grouping, e.g. 528500000000 -> "528.500.000.000". */
function formatFullVN(n: number): string {
  try {
    return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(n);
  } catch {
    return String(Math.round(n * 100) / 100);
  }
}

function formatWithUnit(n: number, donVi?: string): string {
  const s = formatFullVN(n);
  return donVi ? `${s} ${donVi}` : s;
}

/** Vietnamese-abbreviated axis tick, e.g. 1.2 tỷ / 528 triệu / 12,5 nghìn / plain below 1000. */
function formatAbbrevVN(n: number): string {
  const sign = n < 0 ? "-" : "";
  const abs = Math.abs(n);
  const oneDecimal = (v: number) => {
    const r = Math.round(v * 10) / 10;
    return Number.isInteger(r) ? String(r) : r.toFixed(1).replace(".", ",");
  };
  if (abs >= 1e9) return `${sign}${oneDecimal(abs / 1e9)} tỷ`;
  if (abs >= 1e6) return `${sign}${oneDecimal(abs / 1e6)} triệu`;
  if (abs >= 1e3) return `${sign}${oneDecimal(abs / 1e3)} nghìn`;
  return `${sign}${formatFullVN(abs)}`;
}

function ellipsize(s: string, max: number): string {
  if (s.length <= max) return s;
  return s.slice(0, Math.max(1, max - 1)) + "…";
}

/** "Nice" axis ticks (~4-5 gridlines), always including 0. */
function niceTicks(max: number, count = 5): number[] {
  if (!Number.isFinite(max) || max <= 0) return [0, 1];
  const rawStep = max / (count - 1);
  const mag = Math.pow(10, Math.floor(Math.log10(rawStep)));
  const norm = rawStep / mag;
  const niceNorm = norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10;
  const step = niceNorm * mag;
  const niceMax = Math.ceil(max / step) * step;
  const ticks: number[] = [];
  for (let v = 0; v <= niceMax + step / 1e6; v += step) ticks.push(Math.round(v * 1e6) / 1e6);
  return ticks;
}

function seriesColor(index: number): string {
  if (index === 0) return ACCENT;
  return PALETTE[(index - 1) % PALETTE.length];
}

/* ---------------------------------------------------------------------- */
/* Legend packing (character-width heuristic — no DOM measurement, so this */
/* renders identically server-side via renderToStaticMarkup)               */
/* ---------------------------------------------------------------------- */

interface LegendEntry {
  label: string;
  color: string;
}

interface LegendRow {
  items: (LegendEntry & { x: number; w: number })[];
  width: number;
}

function layoutLegend(entries: LegendEntry[], maxWidth: number): LegendRow[] {
  const fontSize = 10.5;
  const swatch = 9;
  const gapAfterSwatch = 5;
  const itemGap = 16;
  const charW = fontSize * 0.58;

  const widths = entries.map((e) => swatch + gapAfterSwatch + e.label.length * charW);

  const rows: LegendEntry[][] = [];
  let current: LegendEntry[] = [];
  let currentW = 0;
  entries.forEach((e, i) => {
    const w = widths[i];
    const addW = current.length === 0 ? w : w + itemGap;
    if (current.length > 0 && currentW + addW > maxWidth) {
      rows.push(current);
      current = [e];
      currentW = w;
    } else {
      current.push(e);
      currentW += addW;
    }
  });
  if (current.length > 0) rows.push(current);

  return rows.map((row) => {
    let x = 0;
    const items = row.map((e) => {
      const idx = entries.indexOf(e);
      const w = widths[idx];
      const item = { ...e, x, w };
      x += w + itemGap;
      return item;
    });
    return { items, width: x - itemGap };
  });
}

function Legend({ entries, cx, y, maxWidth }: { entries: LegendEntry[]; cx: number; y: number; maxWidth: number }): ReactNode {
  const rows = layoutLegend(entries, maxWidth);
  const rowH = 17;
  return (
    <g>
      {rows.map((row, ri) => {
        const startX = cx - row.width / 2;
        const rowY = y + ri * rowH;
        return (
          <g key={ri}>
            {row.items.map((it, ii) => (
              <g key={ii} transform={`translate(${startX + it.x}, ${rowY})`}>
                <rect x={0} y={-8} width={9} height={9} rx={2} fill={it.color} />
                <text x={14} y={0} fontSize={10.5} fill="currentColor" fillOpacity={0.75}>
                  {it.label}
                </text>
              </g>
            ))}
          </g>
        );
      })}
    </g>
  );
}

/* ---------------------------------------------------------------------- */
/* Layout                                                                   */
/* ---------------------------------------------------------------------- */

interface Layout {
  height: number;
  content: ReactNode;
}

const textStyle: CSSProperties = { fontFamily: "inherit" };

function buildLayout(spec: ChartSpec): Layout {
  if (spec.loai === "cot") return buildBarLayout(spec, false);
  if (spec.loai === "cot_ngang") return buildBarLayout(spec, true);
  if (spec.loai === "duong") return buildLineLayout(spec);
  return buildPieLayout(spec);
}

function Header({ tieu_de, don_vi }: { tieu_de?: string; don_vi?: string }): { node: ReactNode; height: number } {
  if (!tieu_de && !don_vi) return { node: null, height: 4 };
  const y = 14;
  return {
    height: 24,
    node: (
      <g style={textStyle}>
        {tieu_de && (
          <text x={10} y={y} fontSize={13} fontWeight={600} fill="currentColor" fillOpacity={0.92}>
            {ellipsize(tieu_de, 70)}
          </text>
        )}
        {don_vi && (
          <text x={VB_W - 10} y={y} fontSize={10.5} fill="currentColor" fillOpacity={0.55} textAnchor="end">
            Đơn vị: {don_vi}
          </text>
        )}
      </g>
    ),
  };
}

function Footnote({ ghi_chu, y }: { ghi_chu?: string; y: number }): ReactNode {
  if (!ghi_chu) return null;
  return (
    <text x={10} y={y} fontSize={10} fill="currentColor" fillOpacity={0.5}>
      {ellipsize(ghi_chu, 90)}
    </text>
  );
}

/* -- Vertical / horizontal grouped bars ---------------------------------- */

function buildBarLayout(spec: ChartSpec, horizontal: boolean): Layout {
  const header = Header({ tieu_de: spec.tieu_de, don_vi: spec.don_vi });
  const nCats = spec.nhan.length;
  const nSeries = spec.chuoi.length;
  const showLegend = true;
  const legendEntries: LegendEntry[] = spec.chuoi.map((s, i) => ({ label: s.ten, color: seriesColor(i) }));
  const legendRows = showLegend ? layoutLegend(legendEntries, VB_W - 20).length : 0;
  const legendH = legendRows > 0 ? legendRows * 17 + 8 : 0;
  const footnoteH = spec.ghi_chu ? 16 : 0;

  const maxVal = Math.max(0, ...spec.chuoi.flatMap((s) => s.gia_tri));
  const ticks = niceTicks(maxVal || 1);
  const niceMax = ticks[ticks.length - 1] || 1;

  if (!horizontal) {
    const padL = 46;
    const padR = 14;
    const longLabel = spec.nhan.some((n) => n.length > 8);
    const axisLabelH = longLabel ? 34 : 16;
    const plotTop = header.height + 6;
    const plotH = 128;
    const plotBottom = plotTop + plotH;
    const height = plotBottom + axisLabelH + legendH + footnoteH + 10;

    const plotW = VB_W - padL - padR;
    const catW = plotW / nCats;
    const groupPad = 0.22;
    const barsAreaW = catW * (1 - groupPad);
    const barGap = nSeries > 1 ? 2 : 0;
    const barW = Math.max(2, (barsAreaW - barGap * (nSeries - 1)) / nSeries);

    const yFor = (v: number) => plotBottom - (Math.max(0, v) / niceMax) * plotH;

    return {
      height,
      content: (
        <>
          {header.node}
          {/* gridlines + y ticks */}
          {ticks.map((t, i) => {
            const y = yFor(t);
            return (
              <g key={i}>
                <line x1={padL} y1={y} x2={VB_W - padR} y2={y} stroke="currentColor" strokeOpacity={0.12} strokeWidth={1} />
                <text x={padL - 6} y={y + 3} fontSize={9.5} fill="currentColor" fillOpacity={0.55} textAnchor="end">
                  {formatAbbrevVN(t)}
                </text>
              </g>
            );
          })}
          {/* bars */}
          {spec.nhan.map((cat, ci) => {
            const groupX = padL + ci * catW + (catW - barsAreaW) / 2;
            return (
              <g key={ci}>
                {spec.chuoi.map((s, si) => {
                  const v = s.gia_tri[ci] ?? 0;
                  const barH = Math.max(0, plotBottom - yFor(v));
                  const x = groupX + si * (barW + barGap);
                  const r = Math.min(4, barW / 2);
                  return (
                    <rect
                      key={si}
                      x={x}
                      y={yFor(v)}
                      width={barW}
                      height={barH}
                      rx={r}
                      fill={seriesColor(si)}
                    >
                      <title>{`${cat} · ${s.ten}: ${formatWithUnit(v, spec.don_vi)}`}</title>
                    </rect>
                  );
                })}
                {/* category label */}
                {longLabel ? (
                  <text
                    x={groupX + barsAreaW / 2}
                    y={plotBottom + 12}
                    fontSize={9.5}
                    fill="currentColor"
                    fillOpacity={0.65}
                    textAnchor="end"
                    transform={`rotate(-30 ${groupX + barsAreaW / 2} ${plotBottom + 12})`}
                  >
                    {ellipsize(cat, 16)}
                  </text>
                ) : (
                  <text x={groupX + barsAreaW / 2} y={plotBottom + 14} fontSize={9.5} fill="currentColor" fillOpacity={0.65} textAnchor="middle">
                    {ellipsize(cat, 12)}
                  </text>
                )}
              </g>
            );
          })}
          {/* baseline */}
          <line x1={padL} y1={plotBottom} x2={VB_W - padR} y2={plotBottom} stroke="currentColor" strokeOpacity={0.25} strokeWidth={1} />
          {showLegend && <Legend entries={legendEntries} cx={VB_W / 2} y={plotBottom + axisLabelH + 14} maxWidth={VB_W - 20} />}
          <Footnote ghi_chu={spec.ghi_chu} y={height - 4} />
        </>
      ),
    };
  }

  // horizontal bars: category labels on the left, numeric axis at the bottom
  const padL = 96;
  const padR = 14;
  const plotTop = header.height + 4;
  const rowH = 26;
  const plotH = nCats * rowH;
  const plotBottom = plotTop + plotH;
  const axisLabelH = 16;
  const height = plotBottom + axisLabelH + legendH + footnoteH + 10;
  const plotW = VB_W - padL - padR;

  const xFor = (v: number) => padL + (Math.max(0, v) / niceMax) * plotW;
  const barGap = nSeries > 1 ? 2 : 0;
  const bandH = rowH * 0.72;
  const barH = Math.max(2, (bandH - barGap * (nSeries - 1)) / nSeries);

  return {
    height,
    content: (
      <>
        {header.node}
        {ticks.map((t, i) => {
          const x = xFor(t);
          return (
            <g key={i}>
              <line x1={x} y1={plotTop} x2={x} y2={plotBottom} stroke="currentColor" strokeOpacity={0.12} strokeWidth={1} />
              <text x={x} y={plotBottom + 12} fontSize={9.5} fill="currentColor" fillOpacity={0.55} textAnchor="middle">
                {formatAbbrevVN(t)}
              </text>
            </g>
          );
        })}
        {spec.nhan.map((cat, ci) => {
          const rowY = plotTop + ci * rowH;
          const bandTop = rowY + (rowH - bandH) / 2;
          return (
            <g key={ci}>
              <text x={padL - 8} y={rowY + rowH / 2 + 3} fontSize={9.5} fill="currentColor" fillOpacity={0.65} textAnchor="end">
                {ellipsize(cat, 14)}
              </text>
              {spec.chuoi.map((s, si) => {
                const v = s.gia_tri[ci] ?? 0;
                const w = Math.max(0, xFor(v) - padL);
                const y = bandTop + si * (barH + barGap);
                const r = Math.min(4, barH / 2);
                return (
                  <rect key={si} x={padL} y={y} width={w} height={barH} rx={r} fill={seriesColor(si)}>
                    <title>{`${cat} · ${s.ten}: ${formatWithUnit(v, spec.don_vi)}`}</title>
                  </rect>
                );
              })}
            </g>
          );
        })}
        <line x1={padL} y1={plotTop} x2={padL} y2={plotBottom} stroke="currentColor" strokeOpacity={0.25} strokeWidth={1} />
        {showLegend && <Legend entries={legendEntries} cx={VB_W / 2} y={plotBottom + axisLabelH + 14} maxWidth={VB_W - 20} />}
        <Footnote ghi_chu={spec.ghi_chu} y={height - 4} />
      </>
    ),
  };
}

/* -- Line chart ----------------------------------------------------------- */

function buildLineLayout(spec: ChartSpec): Layout {
  const header = Header({ tieu_de: spec.tieu_de, don_vi: spec.don_vi });
  const nCats = spec.nhan.length;
  const legendEntries: LegendEntry[] = spec.chuoi.map((s, i) => ({ label: s.ten, color: seriesColor(i) }));
  const legendRows = layoutLegend(legendEntries, VB_W - 20).length;
  const legendH = legendRows * 17 + 8;
  const footnoteH = spec.ghi_chu ? 16 : 0;

  const maxVal = Math.max(0, ...spec.chuoi.flatMap((s) => s.gia_tri));
  const ticks = niceTicks(maxVal || 1);
  const niceMax = ticks[ticks.length - 1] || 1;

  const padL = 46;
  const padR = 14;
  const longLabel = spec.nhan.some((n) => n.length > 8);
  const axisLabelH = longLabel ? 34 : 16;
  const plotTop = header.height + 6;
  const plotH = 128;
  const plotBottom = plotTop + plotH;
  const height = plotBottom + axisLabelH + legendH + footnoteH + 10;

  const plotW = VB_W - padL - padR;
  const xFor = (ci: number) => (nCats === 1 ? padL + plotW / 2 : padL + (ci / (nCats - 1)) * plotW);
  const yFor = (v: number) => plotBottom - (Math.max(0, v) / niceMax) * plotH;

  return {
    height,
    content: (
      <>
        {header.node}
        {ticks.map((t, i) => {
          const y = yFor(t);
          return (
            <g key={i}>
              <line x1={padL} y1={y} x2={VB_W - padR} y2={y} stroke="currentColor" strokeOpacity={0.12} strokeWidth={1} />
              <text x={padL - 6} y={y + 3} fontSize={9.5} fill="currentColor" fillOpacity={0.55} textAnchor="end">
                {formatAbbrevVN(t)}
              </text>
            </g>
          );
        })}
        {spec.nhan.map((cat, ci) => {
          const x = xFor(ci);
          return longLabel ? (
            <text
              key={ci}
              x={x}
              y={plotBottom + 12}
              fontSize={9.5}
              fill="currentColor"
              fillOpacity={0.65}
              textAnchor="end"
              transform={`rotate(-30 ${x} ${plotBottom + 12})`}
            >
              {ellipsize(cat, 16)}
            </text>
          ) : (
            <text key={ci} x={x} y={plotBottom + 14} fontSize={9.5} fill="currentColor" fillOpacity={0.65} textAnchor="middle">
              {ellipsize(cat, 12)}
            </text>
          );
        })}
        <line x1={padL} y1={plotBottom} x2={VB_W - padR} y2={plotBottom} stroke="currentColor" strokeOpacity={0.25} strokeWidth={1} />
        {spec.chuoi.map((s, si) => {
          const points = s.gia_tri.map((v, ci) => `${xFor(ci)},${yFor(v)}`).join(" ");
          const color = seriesColor(si);
          return (
            <g key={si}>
              <polyline points={points} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
              {s.gia_tri.map((v, ci) => (
                <circle key={ci} cx={xFor(ci)} cy={yFor(v)} r={4} fill={color} stroke="var(--surface, #fff)" strokeWidth={2}>
                  <title>{`${spec.nhan[ci]} · ${s.ten}: ${formatWithUnit(v, spec.don_vi)}`}</title>
                </circle>
              ))}
            </g>
          );
        })}
        <Legend entries={legendEntries} cx={VB_W / 2} y={plotBottom + axisLabelH + 14} maxWidth={VB_W - 20} />
        <Footnote ghi_chu={spec.ghi_chu} y={height - 4} />
      </>
    ),
  };
}

/* -- Pie / donut ------------------------------------------------------------ */

function buildPieLayout(spec: ChartSpec): Layout {
  const header = Header({ tieu_de: spec.tieu_de, don_vi: spec.don_vi });
  const values = spec.chuoi[0]?.gia_tri ?? spec.nhan.map(() => 0);
  const total = values.reduce((a, b) => a + Math.max(0, b), 0);

  const legendEntries: LegendEntry[] = spec.nhan.map((n, i) => ({ label: n, color: seriesColor(i) }));
  const legendRows = layoutLegend(legendEntries, VB_W - 20).length;
  const legendH = legendRows * 17 + 8;
  const footnoteH = spec.ghi_chu ? 16 : 0;

  const plotTop = header.height + 4;
  const plotH = 150;
  const cx = VB_W / 2;
  const cy = plotTop + plotH / 2;
  const outerR = plotH / 2 - 4;
  const innerR = outerR * 0.58;
  const height = plotTop + plotH + legendH + footnoteH + 10;

  let angle = -Math.PI / 2; // start at 12 o'clock
  const slices = values.map((raw, i) => {
    const v = Math.max(0, raw);
    const frac = total > 0 ? v / total : 0;
    const start = angle;
    const end = angle + frac * Math.PI * 2;
    angle = end;
    return { v, frac, start, end, color: seriesColor(i), label: spec.nhan[i] };
  });

  const arcPath = (start: number, end: number, rOuter: number, rInner: number) => {
    const full = end - start >= Math.PI * 2 - 1e-6;
    const safeEnd = full ? start + Math.PI * 2 - 1e-4 : end;
    const p = (r: number, a: number) => [cx + r * Math.cos(a), cy + r * Math.sin(a)];
    const [x1, y1] = p(rOuter, start);
    const [x2, y2] = p(rOuter, safeEnd);
    const [x3, y3] = p(rInner, safeEnd);
    const [x4, y4] = p(rInner, start);
    const large = safeEnd - start > Math.PI ? 1 : 0;
    return [
      `M ${x1} ${y1}`,
      `A ${rOuter} ${rOuter} 0 ${large} 1 ${x2} ${y2}`,
      `L ${x3} ${y3}`,
      `A ${rInner} ${rInner} 0 ${large} 0 ${x4} ${y4}`,
      "Z",
    ].join(" ");
  };

  return {
    height,
    content: (
      <>
        {header.node}
        {slices.map((s, i) => {
          if (s.frac <= 0) return null;
          const mid = (s.start + s.end) / 2;
          const labelR = (outerR + innerR) / 2;
          const lx = cx + labelR * Math.cos(mid);
          const ly = cy + labelR * Math.sin(mid);
          const pct = Math.round(s.frac * 1000) / 10;
          return (
            <g key={i}>
              <path d={arcPath(s.start, s.end, outerR, innerR)} fill={s.color}>
                <title>{`${s.label}: ${formatWithUnit(s.v, spec.don_vi)} (${pct.toLocaleString("vi-VN")}%)`}</title>
              </path>
              {s.frac >= 0.05 && (
                <text x={lx} y={ly} fontSize={10} fontWeight={600} fill="#fff" textAnchor="middle" dominantBaseline="middle">
                  {pct.toLocaleString("vi-VN")}%
                </text>
              )}
            </g>
          );
        })}
        <text x={cx} y={cy - 4} fontSize={11.5} fontWeight={700} fill="currentColor" fillOpacity={0.85} textAnchor="middle">
          {formatAbbrevVN(total)}
        </text>
        {spec.don_vi && (
          <text x={cx} y={cy + 11} fontSize={9} fill="currentColor" fillOpacity={0.55} textAnchor="middle">
            {spec.don_vi}
          </text>
        )}
        <Legend entries={legendEntries} cx={VB_W / 2} y={plotTop + plotH + 14} maxWidth={VB_W - 20} />
        <Footnote ghi_chu={spec.ghi_chu} y={height - 4} />
      </>
    ),
  };
}
