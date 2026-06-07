import { ContactEmailButton } from "../commercial/ContactEmailButton";
import {
  extractEmailsFromWarning,
  parseWarningSegments,
} from "../../lib/warningEmailLinks";

export type OperatorWarningEntry =
  | string
  | {
      display: string;
      parseText: string;
    };

function normalizeWarningEntry(entry: OperatorWarningEntry): {
  display: string;
  parseText: string;
} {
  if (typeof entry === "string") {
    return { display: entry, parseText: entry };
  }
  return entry;
}

function WarningLine({
  display,
  parseText,
  onContactSelect,
}: {
  display: string;
  parseText: string;
  onContactSelect: (email: string) => void;
}) {
  const parseEmails = extractEmailsFromWarning(parseText);
  const displayHasInlineEmail = parseEmails.some((email) =>
    display.toLowerCase().includes(email.toLowerCase()),
  );

  if (displayHasInlineEmail && display === parseText) {
    const segments = parseWarningSegments(parseText);
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

  const trailingEmails = parseEmails.filter(
    (email) => !display.toLowerCase().includes(email.toLowerCase()),
  );

  return (
    <li className="text-sm text-amber-950">
      <span>{display}</span>
      {trailingEmails.map((email) => (
        <span key={email}>
          {" "}
          (
          <ContactEmailButton
            email={email}
            onSelect={onContactSelect}
            className="inline font-medium text-brand-800 underline decoration-brand-400 underline-offset-2 hover:text-brand-900"
          />
          )
        </span>
      ))}
    </li>
  );
}

export function OperatorWarningsList({
  warnings,
  onContactSelect,
  moreCount = 0,
  title = "Advertencias",
  subtitle,
  showListSafetyNote = true,
}: {
  warnings: OperatorWarningEntry[];
  onContactSelect: (email: string) => void;
  moreCount?: number;
  title?: string;
  subtitle?: string;
  showListSafetyNote?: boolean;
}) {
  if (warnings.length === 0) {
    return null;
  }

  const defaultSubtitle =
    "Los correos abren un perfil de solo lectura (solo GET). Sin enviar ni enlaces mailto desde las advertencias.";

  return (
    <section className="rounded-lg border border-amber-200 bg-amber-50/80 px-4 py-4">
      <h2 className="text-sm font-semibold text-amber-950">{title}</h2>
      {subtitle ? (
        <p className="mt-1 text-xs text-amber-900">{subtitle}</p>
      ) : showListSafetyNote ? (
        <p className="mt-1 text-xs text-amber-900">{defaultSubtitle}</p>
      ) : null}
      <ul className="mt-2 list-disc space-y-1 pl-5">
        {warnings.map((entry) => {
          const { display, parseText } = normalizeWarningEntry(entry);
          return (
            <WarningLine
              key={parseText}
              display={display}
              parseText={parseText}
              onContactSelect={onContactSelect}
            />
          );
        })}
      </ul>
      {moreCount > 0 ? (
        <p className="mt-2 text-xs text-amber-900">+{moreCount} advertencias más</p>
      ) : null}
    </section>
  );
}
