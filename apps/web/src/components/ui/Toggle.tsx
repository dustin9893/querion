"use client";

export default function Toggle({ on, onChange, disabled, label, testId }: {
  on: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
  label?: string;
  testId?: string;
}) {
  return (
    <button type="button" onClick={() => !disabled && onChange(!on)} aria-pressed={on} disabled={disabled}
      aria-label={label} title={label} data-testid={testId}
      className="rounded-full transition-all" style={{ width: 44, height: 24, flexShrink: 0, background: on ? "#22c55e" : "rgba(120,120,120,0.3)", position: "relative", opacity: disabled ? 0.5 : 1, cursor: disabled ? "not-allowed" : "pointer" }}>
      <div className="rounded-full transition-all" style={{ width: 18, height: 18, background: "#fff", position: "absolute", top: 3, left: on ? 23 : 3 }} />
    </button>
  );
}
