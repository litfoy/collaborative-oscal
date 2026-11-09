/** Returns a same-origin relative path or "/" — never an absolute or protocol-relative URL. */
export function safeReturnTo(value: string | null | undefined): string {
  if (!value || value.length > 2048) return "/";
  if (!value.startsWith("/") || value.startsWith("//") || value.startsWith("/\\")) return "/";
  if (/[\u0000-\u001f\u007f\\]/.test(value)) return "/";
  try {
    const parsed = new URL(value, "http://placeholder.invalid");
    if (parsed.origin !== "http://placeholder.invalid") return "/";
    if (parsed.pathname.startsWith("/auth/") || parsed.pathname.startsWith("/bff/")) return "/";
    return `${parsed.pathname}${parsed.search}`;
  } catch {
    return "/";
  }
}

const SAFE_PROTOCOLS = new Set(["http:", "https:", "mailto:"]);

export type SafeHref =
  | { kind: "internal"; href: string }
  | { kind: "external"; href: string }
  | { kind: "blocked" };

/** Classifies a link coming from imported catalog content. Only inert schemes are allowed. */
export function classifyHref(value: string): SafeHref {
  const trimmed = value.trim();
  if (trimmed.startsWith("#")) return { kind: "internal", href: trimmed };
  try {
    const parsed = new URL(trimmed);
    if (SAFE_PROTOCOLS.has(parsed.protocol)) return { kind: "external", href: parsed.href };
  } catch {
    // relative or malformed references are not followed
  }
  return { kind: "blocked" };
}

const INSERT = /\{\{\s*insert:\s*param\s*,\s*([^\s}]+)\s*\}\}/g;

/** Replaces OSCAL parameter insertions with readable labels. Output is plain text only. */
export function renderProse(text: string, labels: Record<string, string | undefined>): string {
  return text.replace(INSERT, (_match, id: string) => `[${labels[id] ?? id}]`);
}

export function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
}

export function isOscalId(value: string): boolean {
  return /^[A-Za-z0-9._:-]{1,128}$/.test(value);
}
