import type { OperatorLabelKind } from "../../lib/operatorLabels";
import { formatOperatorToken } from "../../lib/operatorLabels";

export function TokenLabel({
  token,
  kind,
  className = "rounded bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-800",
}: {
  token: string | null | undefined;
  kind: OperatorLabelKind;
  className?: string;
}) {
  const { label, raw } = formatOperatorToken(token, kind);
  if (!raw) {
    return <span className="text-slate-500">—</span>;
  }
  return (
    <span className={className} title={label}>
      {label}
    </span>
  );
}
