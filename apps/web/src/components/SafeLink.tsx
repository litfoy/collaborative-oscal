import { classifyHref } from "@/lib/safe";

/** Renders a link from imported content only when its scheme is inert. */
export function SafeLink({ href, children }: { href: string; children: React.ReactNode }) {
  const target = classifyHref(href);
  if (target.kind === "blocked") {
    return (
      <span title="This link was not made clickable because its address is not allowed.">
        {children} <span className="muted">(link disabled)</span>
      </span>
    );
  }
  if (target.kind === "internal") {
    return <span>{children}</span>;
  }
  return (
    <a href={target.href} target="_blank" rel="noopener noreferrer nofollow">
      {children}
    </a>
  );
}
