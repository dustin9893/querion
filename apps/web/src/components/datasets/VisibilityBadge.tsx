"use client";

interface Props {
  visibility: "internal" | "public";
  label: string;
}

/** Small pill showing whether a knowledge base is internal (staff only) or public (customer-facing). */
export default function VisibilityBadge({ visibility, label }: Props) {
  const isPublic = visibility === "public";
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
      style={{
        background: isPublic ? "rgba(34,197,94,0.12)" : "rgba(100,116,139,0.14)",
        color: isPublic ? "#16a34a" : "var(--muted)",
        border: `1px solid ${isPublic ? "rgba(34,197,94,0.3)" : "var(--border)"}`,
      }}
    >
      <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
        {isPublic ? (
          <>
            <circle cx="5" cy="5" r="4" stroke="currentColor" strokeWidth="1" />
            <path d="M1 5H9M5 1C6.5 2.5 6.5 7.5 5 9M5 1C3.5 2.5 3.5 7.5 5 9" stroke="currentColor" strokeWidth="0.9" />
          </>
        ) : (
          <>
            <rect x="2" y="4.5" width="6" height="4.5" rx="1" stroke="currentColor" strokeWidth="1" />
            <path d="M3.5 4.5V3.2A1.5 1.5 0 0 1 6.5 3.2V4.5" stroke="currentColor" strokeWidth="1" />
          </>
        )}
      </svg>
      {label}
    </span>
  );
}
