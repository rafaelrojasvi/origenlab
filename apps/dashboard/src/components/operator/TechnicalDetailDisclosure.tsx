type TechnicalDetailDisclosureProps = {
  detail: string;
  label?: string;
};

/** Collapsible secondary technical detail (read-only; native details/summary). */
export function TechnicalDetailDisclosure({
  detail,
  label = "Ver detalle técnico",
}: TechnicalDetailDisclosureProps) {
  if (!detail.trim()) {
    return null;
  }

  return (
    <details className="mt-1 text-xs text-red-800">
      <summary className="cursor-pointer select-none text-red-900 underline decoration-red-300 underline-offset-2 hover:text-red-950">
        {label}
      </summary>
      <p className="mt-1 break-words">{detail}</p>
    </details>
  );
}
