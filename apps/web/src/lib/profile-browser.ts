// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

import type { ProfileBrowserNode } from "./types";
import type { Translate } from "./i18n";

export const MAX_PROFILE_CONTROLS = 10_000;

const LABEL_KEYS: Record<string, Parameters<Translate>[0]> = {
  modal_verb: "profiles.classification",
  sec_level: "profiles.securityLevel",
  effort_level: "profiles.effortLevel",
  tags: "profiles.tags",
  target_object_categories: "profiles.targetObjectCategories",
};

const LABEL_PRIORITY = ["modal_verb", "sec_level", "effort_level", "tags", "target_object_categories"];

export function propertyLabel(name: string, t?: Translate): string {
  const key = LABEL_KEYS[name];
  if (!key) return name;
  if (t) return t(key);
  const englishLabels: Record<string, string> = {
    modal_verb: "Classification",
    sec_level: "Security level",
    effort_level: "Effort level",
    tags: "Tags",
    target_object_categories: "Target object categories",
  };
  return englishLabels[name] ?? name;
}

export function propertyKey(name: string, ns?: string | null): string {
  return JSON.stringify([name, ns ?? ""]);
}

export function indexBrowser(nodes: ProfileBrowserNode[], t?: Translate) {
  const byKey = new Map(nodes.map((node) => [node.key, node]));
  const children = new Map<string | null, ProfileBrowserNode[]>();
  const search = new Map<string, string>();
  const facets = new Map<string, { key: string; name: string; label: string; ns: string; values: Set<string> }>();
  for (const node of nodes) {
    const siblings = children.get(node.parent_key) ?? [];
    siblings.push(node);
    children.set(node.parent_key, siblings);
    search.set(node.key, `${node.id ?? ""}\n${node.title}\n${node.text}\n${node.properties.map((p) => p.value).join("\n")}`.toLocaleLowerCase());
    if (node.kind !== "control") continue;
    for (const prop of node.properties) {
      const key = propertyKey(prop.name, prop.ns);
      const facet = facets.get(key) ?? { key, name: prop.name, label: propertyLabel(prop.name, t), ns: prop.ns ?? "", values: new Set<string>() };
      facet.values.add(prop.value);
      facets.set(key, facet);
    }
  }
  const controls = nodes.filter((node) => node.kind === "control");
  return {
    byKey, children, controls, search,
    facets: [...facets.values()].filter((facet) => facet.values.size <= 100)
      .sort((a, b) => {
        const rank = (facet: typeof a) => {
          const index = LABEL_PRIORITY.indexOf(facet.name);
          return index >= 0 ? index : LABEL_PRIORITY.length;
        };
        return rank(a) - rank(b) || a.label.localeCompare(b.label);
      }),
  };
}

export function inBranch(node: ProfileBrowserNode, branch: string | null): boolean {
  return branch === null || node.key === branch || node.key.startsWith(`${branch}/`);
}

export function matchesProperties(node: ProfileBrowserNode, filters: Record<string, string>): boolean {
  return Object.entries(filters).every(([key, value]) => !value ||
    node.properties.some((prop) => propertyKey(prop.name, prop.ns) === key && prop.value === value));
}
