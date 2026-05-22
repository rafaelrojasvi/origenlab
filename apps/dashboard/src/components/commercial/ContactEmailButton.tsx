/** Opens read-only contact profile drilldown (GET /contacts/{email} only). */

export function ContactEmailButton({
  email,
  label,
  onSelect,
  className,
}: {
  email: string;
  label?: string;
  onSelect: (email: string) => void;
  className?: string;
}) {
  const trimmed = email.trim();
  if (!trimmed || !trimmed.includes("@")) {
    return <span className="text-slate-500">—</span>;
  }

  const display = label?.trim() || trimmed;

  return (
    <button
      type="button"
      onClick={() => onSelect(trimmed)}
      className={
        className ??
        "text-left font-medium text-brand-700 underline decoration-brand-300 underline-offset-2 hover:text-brand-900 hover:decoration-brand-500"
      }
      title="View read-only contact profile"
    >
      {display}
    </button>
  );
}
