interface Props {
  confidence: string;
}

export function ConfidenceBadge({ confidence }: Props) {
  const c = confidence.toLowerCase();
  let tone = "bg-slate-100 text-slate-700";
  if (c.includes("high")) tone = "bg-emerald-100 text-emerald-800";
  else if (c.includes("medium")) tone = "bg-amber-100 text-amber-900";
  else if (c.includes("weak") || c.includes("manual")) tone = "bg-orange-100 text-orange-900";

  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${tone}`}>
      {confidence.replace(/_/g, " ")}
    </span>
  );
}
