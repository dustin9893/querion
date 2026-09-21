"use client";

import Link from "next/link";
import type { DatasetResponse } from "@/lib/api/datasets";
import type { AppAudience } from "@/lib/api/apps";
import VisibilityBadge from "@/components/datasets/VisibilityBadge";

/** Internal knowledge bases picked for a customer assistant (the API rejects them). */
export function blockedDatasets(datasets: DatasetResponse[], ids: string[], audience: AppAudience) {
  return audience === "customer" ? datasets.filter((d) => ids.includes(d.id) && d.visibility !== "public") : [];
}

/** Choose one or more knowledge bases for an assistant; retrieval searches all of them together. */
export default function DatasetPicker({ datasets, value, onChange, audience, compact }: {
  datasets: DatasetResponse[];
  value: string[];
  onChange: (ids: string[]) => void;
  audience: AppAudience;
  compact?: boolean;
}) {
  if (datasets.length === 0) {
    return (
      <p className="text-xs" style={{ color: "var(--muted)" }}>
        Đơn vị chưa có kho tri thức nào. Tạo ở mục <Link href="/datasets" className="underline" style={{ color: "var(--accent)" }}>Kho tri thức</Link>.
      </p>
    );
  }
  const toggle = (id: string) => onChange(value.includes(id) ? value.filter((x) => x !== id) : [...value, id]);

  return (
    <div className="space-y-1.5" data-testid="dataset-picker">
      {datasets.map((ds) => {
        const checked = value.includes(ds.id);
        const allowed = audience !== "customer" || ds.visibility === "public";
        return (
          <label key={ds.id} className={`flex items-center gap-3 rounded-lg px-3 ${compact ? "py-1.5" : "py-2.5"} text-xs`}
            style={{
              background: checked ? "var(--accent-glow)" : "var(--background)",
              border: `1px solid ${checked ? (allowed ? "var(--accent)" : "#ef4444") : "var(--border)"}`,
              opacity: allowed || checked ? 1 : 0.5, cursor: allowed || checked ? "pointer" : "not-allowed",
            }}>
            <input type="checkbox" checked={checked} disabled={!allowed && !checked} onChange={() => toggle(ds.id)}
              data-testid={`pick-dataset-${ds.id}`} />
            <span className="min-w-0 flex-1">
              <span className="flex flex-wrap items-center gap-1.5">
                <span className="font-semibold" style={{ color: "var(--foreground)" }}>{ds.name}</span>
                <VisibilityBadge visibility={ds.visibility} label={ds.visibility === "public" ? "Công khai" : "Nội bộ"} />
                <span style={{ color: "var(--muted)" }}>{ds.document_count} văn bản</span>
              </span>
              {!allowed && (
                <span className="block mt-0.5" style={{ color: "#ef4444" }}>
                  {checked ? "Kho nội bộ — bỏ chọn, trợ lý khách hàng chỉ dùng kho công khai." : "Kho nội bộ — trợ lý khách hàng không dùng được."}
                </span>
              )}
            </span>
          </label>
        );
      })}
    </div>
  );
}
