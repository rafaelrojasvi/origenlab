import { useState } from "react";

export function CopyTextButton({
  label,
  value,
  disabled,
}: {
  label: string;
  value: string;
  disabled?: boolean;
}) {
  const [copied, setCopied] = useState(false);

  if (!value?.trim()) {
    return <span className="text-xs text-[var(--color-muted)]">—</span>;
  }

  return (
    <button
      type="button"
      disabled={disabled}
      className="rounded border border-slate-200 bg-white px-2 py-0.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
      onClick={() => {
        void navigator.clipboard.writeText(value).then(() => {
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1500);
        });
      }}
    >
      {copied ? "Copied" : label}
    </button>
  );
}
