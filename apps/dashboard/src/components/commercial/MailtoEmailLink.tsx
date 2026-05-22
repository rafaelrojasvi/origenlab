/**
 * Email-only mailto links (no subject/body prefills — avoids leaking preview text).
 */

export function buildMailtoHref(email: string): string | null {
  const trimmed = email.trim();
  if (!trimmed || !trimmed.includes("@")) {
    return null;
  }
  if (/[?&]/.test(trimmed)) {
    return null;
  }
  return `mailto:${trimmed}`;
}

export function MailtoEmailLink({ email }: { email: string }) {
  const href = buildMailtoHref(email);
  if (!href) {
    return null;
  }
  return (
    <a
      href={href}
      className="text-xs text-brand-700 underline hover:text-brand-900"
      rel="noopener noreferrer"
      title="Opens your mail client (does not send automatically)"
    >
      mailto
    </a>
  );
}
