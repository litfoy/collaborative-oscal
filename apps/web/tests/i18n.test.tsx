// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import RootLayout from "@/app/layout";
import { AppShell } from "@/components/AppShell";
import { ControlDetailView } from "@/components/ControlDetailView";
import { ImplementationRegister } from "@/components/ImplementationRegister";
import { LanguageSelector } from "@/components/LanguageSelector";
import { ApiError, ERROR_MESSAGES } from "@/lib/errors";
import { createI18n, de, en } from "@/lib/i18n";
import { LOCALE_COOKIE, resolveLocale } from "@/lib/i18n/locale";
import { LocaleProvider } from "@/lib/i18n/provider";
import { getI18n } from "@/lib/i18n/server";
import type { Profile } from "@/lib/types";

import { CATALOG, REVISION, TENANT, control, page } from "./fixtures";

const mocks = vi.hoisted(() => ({ cookie: undefined as string | undefined, refresh: vi.fn(), bffGet: vi.fn(), bffWrite: vi.fn() }));
vi.mock("next/headers", () => ({
  cookies: async () => ({ get: (name: string) => name === "co_locale" && mocks.cookie !== undefined ? { value: mocks.cookie } : undefined }),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: mocks.refresh, replace: vi.fn() }) }));
vi.mock("@/lib/bff-client", () => ({ bffGet: mocks.bffGet, bffWrite: mocks.bffWrite }));

afterEach(() => {
  mocks.cookie = undefined;
  document.cookie = `${LOCALE_COOKIE}=; Path=/; Max-Age=0`;
  document.documentElement.lang = "en";
  vi.clearAllMocks();
});

describe("translation resources", () => {
  it("has the same nonempty keys and interpolation parameters in both languages", () => {
    expect(Object.keys(de).sort()).toEqual(Object.keys(en).sort());
    for (const key of Object.keys(en) as (keyof typeof en)[]) {
      expect(de[key].trim(), key).not.toBe("");
      const placeholders = (value: string) => [...value.matchAll(/\{(\w+)\}/g)].map((match) => match[1]).sort();
      expect(placeholders(de[key]), key).toEqual(placeholders(en[key]));
    }
  });

  it("uses English by default and rejects unsupported cookie values", () => {
    expect(resolveLocale(undefined)).toBe("en");
    expect(resolveLocale("fr")).toBe("en");
    expect(resolveLocale("de")).toBe("de");
    expect(createI18n("en").t("nav.catalogs")).toBe("Catalogs");
    expect(createI18n("en").t("nav.overview")).toBe("Overview");
    expect(createI18n("de").t("workspaceOverview.systemSummary.title")).toBe("Systemueberblick");
  });

  it("falls back to English if a German entry is unavailable", () => {
    const saved = de["nav.catalogs"];
    try {
      Reflect.deleteProperty(de, "nav.catalogs");
      expect(createI18n("de").t("nav.catalogs")).toBe(en["nav.catalogs"]);
    } finally {
      de["nav.catalogs"] = saved;
    }
  });

  it("formats numbers, timestamps and enumeration display labels without changing values", () => {
    const english = createI18n("en");
    const german = createI18n("de");
    expect(english.number(1196)).toBe("1,196");
    expect(german.number(1196)).toBe("1.196");
    expect(german.date("2026-11-16T12:00:00Z")).toContain("16.11.2026");
    expect(english.date("2026-11-16T12:00:00Z")).toContain("Nov 16, 2026");
    expect(german.enumLabel("implemented")).toBe("Umgesetzt");
    expect(german.enumLabel("partial")).toBe("Teilweise umgesetzt");
    expect(german.enumLabel("operational")).toBe("In Betrieb");
    expect(german.enumLabel("policy")).toBe("Richtlinie");
    expect(german.enumLabel("unknown-future-value")).toBe("unknown-future-value");
    expect(german.t("catalogPage.controlOne", { count: german.number(1) })).toBe("1 Anforderung");
    expect(german.t("catalogPage.controlOther", { count: german.number(1196) })).toBe("1.196 Anforderungen");
  });

  it("localizes stable error kinds and retains raw diagnostic details", () => {
    const { errorMessage } = createI18n("de");
    expect(errorMessage(new ApiError("forbidden", 403, ERROR_MESSAGES.forbidden))).toBe(de["errors.forbidden"]);
    const diagnostic = "/catalog/controls/0: ac-1, revision 123";
    expect(errorMessage(new ApiError("invalid", 422, diagnostic))).toContain(diagnostic);
    expect(errorMessage(new Error(diagnostic))).toContain("Diagnosedetails:");
  });
});

describe("locale preference", () => {
  it("renders the cookie locale on the server, including html lang and navigation", async () => {
    expect((await getI18n()).locale).toBe("en");
    mocks.cookie = "de";
    const root = await RootLayout({
      children: <AppShell userName="Original User" currentTenantId={TENANT} demoMode
        tenants={[{ id: TENANT, name: "Original Workspace", slug: "original", role: "viewer", permissions: [] }]}>
        <p>Original content</p>
      </AppShell>,
    });
    const html = renderToStaticMarkup(root);
    expect(html).toContain('<html lang="de">');
    expect(html).toContain("Uebersicht");
    expect(html).toContain("Anforderungskataloge");
    expect(html).toContain("Unsere Maßnahmen");
    expect(html).toContain("Demomodus");
    expect(html).toContain("Original Workspace");
    expect(html).toContain("Original User");
    expect(html).toContain("Original content");
  });

  it("switches without navigating or discarding edits, then persists for subsequent server requests", async () => {
    const user = userEvent.setup();
    const view = render(<LocaleProvider locale="en"><LanguageSelector /><input aria-label="Draft" defaultValue="Original draft" /></LocaleProvider>);
    expect(screen.getByRole("combobox", { name: "Language" })).toHaveValue("en");
    await user.type(screen.getByLabelText("Draft"), " edited");
    await user.selectOptions(screen.getByLabelText("Language"), "de");
    expect(screen.getByLabelText("Sprache")).toHaveValue("de");
    expect(screen.getByRole("combobox", { name: "Sprache" })).toHaveValue("de");
    expect(document.documentElement.lang).toBe("de");
    expect(document.cookie).toContain(`${LOCALE_COOKIE}=de`);
    expect(screen.getByLabelText("Draft")).toHaveValue("Original draft edited");
    expect(mocks.refresh).toHaveBeenCalledOnce();
    mocks.cookie = document.cookie.split(`${LOCALE_COOKIE}=`)[1]?.split(";")[0];
    expect((await getI18n()).locale).toBe("de");
    view.unmount();
    render(<LocaleProvider locale={(await getI18n()).locale}><LanguageSelector /></LocaleProvider>);
    expect(screen.getByLabelText("Sprache")).toHaveValue("de");
    await user.selectOptions(screen.getByLabelText("Sprache"), "en");
    expect(document.cookie).toContain(`${LOCALE_COOKIE}=en`);
  });
});

describe("localized workspaces preserve source data", () => {
  it("leaves normative Catalog content, properties and identifiers untouched", () => {
    const original = control();
    const before = JSON.stringify(original);
    render(<LocaleProvider locale="de"><ControlDetailView control={original} /></LocaleProvider>);
    expect(screen.getByText("Access Policy")).toBeInTheDocument();
    expect(screen.getByText("Nested item")).toBeInTheDocument();
    expect(screen.getAllByText(/ac-1/).length).toBeGreaterThan(0);
    expect(JSON.stringify(original)).toBe(before);
  });

  it("submits original implementation values and authored text with German labels", async () => {
    const profile: Profile = { id: "profile", tenant_id: TENANT, catalog_id: CATALOG, revision_id: REVISION,
      title: "Original Baseline", control_ids: ["ac-1"], created_at: "2026-01-01", updated_at: "2026-01-01",
      concurrency_version: 1 };
    mocks.bffGet.mockImplementation(async (path: string) => {
      if (path.endsWith("implementation-options")) return { organizations: [], people: [] };
      if (path.includes("/controls/") || path.endsWith("/control")) return control();
      return page([]);
    });
    mocks.bffWrite.mockResolvedValue({ ...profile, id: "implementation", oscal_control_id: "ac-1",
      description: "Original authored description", status: "implemented", evidence_references: [], responsibilities: [] });
    const user = userEvent.setup();
    render(<LocaleProvider locale="de"><ImplementationRegister tenantId={TENANT} profile={profile}
      canWrite initialControlId="ac-1" onBack={vi.fn()} /></LocaleProvider>);
    const option = await screen.findByRole("option", { name: "Umgesetzt" });
    expect(option).toHaveValue("implemented");
    const description = screen.getByRole("textbox", { name: "Beschreibung der Umsetzung" });
    await user.type(description, "Original authored description");
    await user.selectOptions(option.closest("select")!, "implemented");
    await user.click(screen.getByRole("button", { name: "Umsetzung speichern" }));
    await waitFor(() => expect(mocks.bffWrite).toHaveBeenCalledWith(
      "POST", `tenants/${TENANT}/implementations`, expect.objectContaining({
        catalog_id: CATALOG, revision_id: REVISION, oscal_control_id: "ac-1",
        description: "Original authored description", status: "implemented",
      }),
    ));
  });
});