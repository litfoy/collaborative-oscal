// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

"use client";

import { classifyHref } from "@/lib/safe";
import { useI18n } from "@/lib/i18n/provider";

/** Renders a link from imported content only when its scheme is inert. */
export function SafeLink({ href, children }: { href: string; children: React.ReactNode }) {
  const { t } = useI18n();
  const target = classifyHref(href);
  if (target.kind === "blocked") {
    return (
      <span title={t("common.linkBlocked")}>
        {children} <span className="muted">{t("common.linkDisabled")}</span>
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
