import type { ProfileBrowserNode } from "./types";

export const MAX_PROFILE_CONTROLS = 10_000;

const LABELS: Record<string, string> = {
  modal_verb: "Classification",
  sec_level: "Security level",
  effort_level: "Effort level",
  tags: "Tags",
  target_object_categories: "Target object categories",
};

export function propertyLabel(name: string): string {
  return LABELS[name] ?? name;
}

export function propertyKey(name: string, ns?: string | null): string {
  return JSON.stringify([name, ns ?? ""]);
}

export function indexBrowser(nodes: ProfileBrowserNode[]) {
  const byKey = new Map(nodes.map((node) => [node.key, node]));
  const children = new Map<string | null, ProfileBrowserNode[]>();
  const search = new Map<string, string>();
  const facets = new Map<string, { key: string; label: string; ns: string; values: Set<string> }>();
  for (const node of nodes) {
    const siblings = children.get(node.parent_key) ?? [];
    siblings.push(node);
    children.set(node.parent_key, siblings);
    search.set(node.key, `${node.id ?? ""}\n${node.title}\n${node.text}\n${node.properties.map((p) => p.value).join("\n")}`.toLocaleLowerCase());
    if (node.kind !== "control") continue;
    for (const prop of node.properties) {
      const key = propertyKey(prop.name, prop.ns);
      const facet = facets.get(key) ?? { key, label: propertyLabel(prop.name), ns: prop.ns ?? "", values: new Set<string>() };
      facet.values.add(prop.value);
      facets.set(key, facet);
    }
  }
  const controls = nodes.filter((node) => node.kind === "control");
  return {
    byKey, children, controls, search,
    facets: [...facets.values()].filter((facet) => facet.values.size <= 100)
      .sort((a, b) => {
        const priority = Object.values(LABELS);
        const rank = (label: string) => priority.includes(label) ? priority.indexOf(label) : priority.length;
        return rank(a.label) - rank(b.label) || a.label.localeCompare(b.label);
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
