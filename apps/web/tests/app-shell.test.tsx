// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/AppShell";
import { LocaleProvider } from "@/lib/i18n/provider";

const TENANT = "11111111-1111-4111-8111-111111111111";
const OTHER_TENANT = "22222222-2222-4222-8222-222222222222";

const mocks = vi.hoisted(() => ({
  pathname: "/",
  refresh: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => mocks.pathname,
  useRouter: () => ({ refresh: mocks.refresh, replace: vi.fn() }),
}));

function renderShell({
  locale = "en",
  currentTenantId = TENANT,
  demoMode = false,
  children = <p>CONTENT</p>,
}: {
  locale?: "en" | "de";
  currentTenantId?: string | null;
  demoMode?: boolean;
  children?: ReactNode;
}) {
  return render(
    <LocaleProvider locale={locale}>
      <AppShell
        userName="Alice"
        demoMode={demoMode}
        currentTenantId={currentTenantId ?? undefined}
        tenants={[
          { id: TENANT, name: "Alpha", slug: "alpha", role: "viewer", permissions: ["catalog:read"] },
          { id: OTHER_TENANT, name: "Beta", slug: "beta", role: "viewer", permissions: ["catalog:read"] },
        ]}
      >
        {children}
      </AppShell>
    </LocaleProvider>,
  );
}

describe("app shell navigation", () => {
  beforeEach(() => {
    mocks.pathname = `/t/${TENANT}`;
    vi.clearAllMocks();
  });

  it("renders grouped navigation with expected tenant-scoped destinations", () => {
    renderShell({});

    const nav = screen.getByRole("navigation", { name: "Workspace navigation" });
    expect(screen.getByRole("heading", { level: 2, name: "Workspace" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Explorer" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Libraries & Modeling" })).toBeInTheDocument();
    expect(screen.getByText("Assessments")).toBeInTheDocument();

    expect(screen.getByRole("link", { name: "Overview" })).toHaveAttribute("href", `/t/${TENANT}`);
    expect(screen.getByRole("link", { name: "Systems" })).toHaveAttribute("href", `/t/${TENANT}/systems`);
    expect(screen.getByRole("link", { name: "Requirements & Measures" })).toHaveAttribute("href", `/t/${TENANT}/compliance-explorer`);
    expect(screen.getByRole("link", { name: "Assessment plans" })).toHaveAttribute("href", `/t/${TENANT}/assessment-plans`);
    expect(screen.getByRole("link", { name: "Assessment results" })).toHaveAttribute("href", `/t/${TENANT}/assessment-results`);
    expect(screen.getByRole("link", { name: "Catalogs" })).toHaveAttribute("href", `/t/${TENANT}/catalogs`);
    expect(screen.getByRole("link", { name: "Profiles" })).toHaveAttribute("href", `/t/${TENANT}/profiles`);
    expect(screen.getByRole("link", { name: "Component Definitions" })).toHaveAttribute("href", `/t/${TENANT}/measures`);
    expect(screen.getByRole("link", { name: "Control mappings" })).toHaveAttribute("href", `/t/${TENANT}/mappings`);

    expect(nav).toBeInTheDocument();
  });

  it("uses active state from the current path without confusing nested system routes", () => {
    mocks.pathname = `/t/${TENANT}/systems`;
    let view = renderShell({});
    expect(screen.getByRole("link", { name: "Systems" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Assessment plans" })).not.toHaveAttribute("aria-current");

    view.unmount();
    mocks.pathname = `/t/${TENANT}/systems/sys-1/assessment-plans/plan-1`;
    view = renderShell({});
    expect(screen.getByRole("link", { name: "Systems" })).toHaveAttribute("aria-current", "location");
    expect(screen.getByRole("link", { name: "Assessment plans" })).not.toHaveAttribute("aria-current");

    view.unmount();
    mocks.pathname = `/t/${TENANT}/assessment-plans`;
    view = renderShell({});
    expect(screen.getByRole("link", { name: "Systems" })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("link", { name: "Assessment plans" })).toHaveAttribute("aria-current", "page");

    view.unmount();
    mocks.pathname = `/t/${TENANT}/assessment-plans/plan-1`;
    renderShell({});
    expect(screen.getByRole("link", { name: "Assessment plans" })).toHaveAttribute("aria-current", "location");
  });

  it("keeps content mounted while mobile navigation toggles", async () => {
    const user = userEvent.setup();
    renderShell({ children: <input aria-label="Draft" defaultValue="Original draft" /> });

    const toggle = screen.getByRole("button", { name: "Open navigation" });
    const controls = toggle.getAttribute("aria-controls");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(controls).toBeTruthy();
    expect(document.getElementById(controls!)).toBeInTheDocument();

    await user.type(screen.getByLabelText("Draft"), " edited");
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: "Close navigation" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Close navigation" }));
    expect(screen.getByLabelText("Draft")).toHaveValue("Original draft edited");
  });

  it("preserves workspace switching, language selection, demo mode, and sign-out behavior", () => {
    const { unmount } = renderShell({ demoMode: false });
    expect(screen.getByText("Workspace: Alpha")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Switch workspace" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("combobox", { name: "Language" })).toBeInTheDocument();
    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign out" }).closest("form")).toHaveAttribute("method", "post");

    unmount();
    renderShell({ demoMode: true });
    expect(screen.getByText("Demo Mode")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sign out" })).toBeNull();
  });

  it("does not render tenant navigation when no authorized workspace is selected", () => {
    renderShell({ currentTenantId: null });
    expect(screen.queryByRole("navigation", { name: "Workspace navigation" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Overview" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Open navigation" })).toBeNull();
    expect(screen.getByRole("combobox", { name: "Language" })).toBeInTheDocument();
  });

  it("renders German labels for section headings and links", () => {
    renderShell({ locale: "de" });
    expect(screen.getByRole("navigation", { name: "Arbeitsbereichsnavigation" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Arbeitsbereich" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Bibliotheken & Modellierung" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Anforderungen & Maßnahmen" })).toHaveAttribute("href", `/t/${TENANT}/compliance-explorer`);
    expect(screen.getByRole("link", { name: "Komponentendefinitionen" })).toHaveAttribute("href", `/t/${TENANT}/measures`);
    expect(screen.getByRole("link", { name: "Prüfpläne" })).toHaveAttribute("href", `/t/${TENANT}/assessment-plans`);
    expect(screen.getByRole("link", { name: "Prüfergebnisse" })).toHaveAttribute("href", `/t/${TENANT}/assessment-results`);
  });
});







