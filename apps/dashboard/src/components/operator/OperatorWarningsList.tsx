import { ContactEmailButton } from "../commercial/ContactEmailButton";
import { parseWarningSegments } from "../../lib/warningEmailLinks";

function WarningLine({
  text,
  onContactSelect,
}: {
  text: string;
  onContactSelect: (email: string) => void;
}) {
  const segments = parseWarningSegments(text);
  return (
    <li className="text-sm text-amber-950">
      {segments.map((seg, index) =>
        seg.type === "email" ? (
          <ContactEmailButton
            key={`${index}-${seg.value}`}
            email={seg.value}
            onSelect={onContactSelect}
            className="inline font-medium text-brand-800 underline decoration-brand-400 underline-offset-2 hover:text-brand-900"
          />
        ) : (
          <span key={`${index}-t`}>{seg.value}</span>
        ),
      )}
    </li>
  );
}

export function OperatorWarningsList({
  warnings,
  onContactSelect,
  moreCount = 0,
}: {
  warnings: string[];
  onContactSelect: (email: string) => void;
  moreCount?: number;
}) {
  if (warnings.length === 0) {
    return null;
  }

  return (
    <section className="rounded-lg border border-amber-200 bg-amber-50/80 px-4 py-4">
      <h2 className="text-sm font-semibold text-amber-950">Warnings</h2>
      <p className="mt-1 text-xs text-amber-900">
        Email addresses open a read-only contact profile (GET only). No send or mailto from
        warnings.
      </p>
      <ul className="mt-2 list-disc space-y-1 pl-5">
        {warnings.map((w) => (
          <WarningLine key={w} text={w} onContactSelect={onContactSelect} />
        ))}
      </ul>
      {moreCount > 0 ? (
        <p className="mt-2 text-xs text-amber-900">+{moreCount} more warnings</p>
      ) : null}
    </section>
  );
}
