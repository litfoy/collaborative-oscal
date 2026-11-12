import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CatalogImport } from "@/components/CatalogImport";
import { CATALOG, REVISION, TENANT, catalog, jsonResponse, page } from "./fixtures";

const refresh = vi.fn();
const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, replace }) }));

function selectedFile(content: string) {
  const file = new File([content], "catalog.json", { type: "application/json" });
  Object.defineProperty(file, "text", { value: async () => content });
  return file;
}

const content = JSON.stringify({ catalog: { uuid: "source-uuid", metadata: {
  title: "Test catalog", version: "2025", "oscal-version": "1.2.1",
} } });

async function chooseFile() {
  const user = userEvent.setup();
  render(<CatalogImport tenantId={TENANT} />);
  await user.click(screen.getByRole("button", { name: "Import catalog" }));
  const file = selectedFile(content);
  await user.upload(screen.getByLabelText(/select or drop/i), file);
  await screen.findByText("Test catalog");
  return { user, file };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("catalog import", () => {
  it("uploads the original file once, refreshes the list, and links to the returned revision", async () => {
    let resolve!: (response: Response) => void;
    const fetchMock = vi.fn((_url: string, _init?: RequestInit) => new Promise<Response>((done) => { resolve = done; }));
    vi.stubGlobal("fetch", fetchMock);
    const { user, file } = await chooseFile();
    expect(screen.getByText("2025")).toBeInTheDocument();
    expect(screen.getByText("1.2.1")).toBeInTheDocument();
    const form = screen.getByRole("button", { name: "Import catalog" }).closest("form")!;
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][1]?.body).toBe(file);
    expect(screen.getByRole("button", { name: "Importing…" })).toBeDisabled();
    resolve(jsonResponse({ catalog_id: CATALOG, catalog_name: "Server catalog", revision_id: REVISION,
      revision_number: 2, oscal_document_uuid: "source-uuid", oscal_version: "1.2.1",
      source_version: "2025", control_count: 7, created: true }));
    expect(await screen.findByText(/Server catalog.*Revision 2/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open imported revision/i }))
      .toHaveAttribute("href", `/t/${TENANT}/catalogs/${CATALOG}?revision=${REVISION}`);
    expect(refresh).toHaveBeenCalledOnce();
    expect(replace).toHaveBeenCalledWith(`/t/${TENANT}/catalogs`, { scroll: false });
    await user.click(screen.getByRole("button", { name: "Close" }));
  });

  it("shows backend validation errors and preserves the file for retry", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({
      detail: { message: "Catalog validation failed.", errors: [
        { code: "UNSUPPORTED_OSCAL_VERSION", message: "Unsupported OSCAL version.", path: "/catalog/metadata/oscal-version" },
      ] },
    }, 422)));
    const { user } = await chooseFile();
    await user.click(screen.getByRole("button", { name: "Import catalog" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Unsupported OSCAL version.");
    expect(screen.getByText(/catalog.json/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Import catalog" })).toBeEnabled();
  });

  it("imports a revision into an explicitly selected catalog and reports duplicates", async () => {
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => init?.method === "POST"
      ? jsonResponse({ catalog_id: CATALOG, catalog_name: "Server catalog", revision_id: REVISION,
        revision_number: 1, oscal_document_uuid: "source-uuid", oscal_version: "1.2.1",
        source_version: "2025", control_count: 7, created: false })
      : jsonResponse(page([catalog()])));
    vi.stubGlobal("fetch", fetchMock);
    const { user } = await chooseFile();
    await user.click(screen.getByRole("radio", { name: /existing catalog/i }));
    await screen.findByRole("option", { name: /Sample Security Practices/ });
    await user.selectOptions(screen.getByLabelText("Target catalog"), CATALOG);
    await user.click(screen.getByRole("button", { name: "Import catalog" }));
    expect(await screen.findByText(/already exists/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      `/bff/tenants/${TENANT}/catalogs/${CATALOG}/import`, expect.objectContaining({ method: "POST" }),
    );
  });

  it("rejects malformed or non-catalog JSON before sending", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<CatalogImport tenantId={TENANT} />);
    await user.click(screen.getByRole("button", { name: "Import catalog" }));
    await user.upload(screen.getByLabelText(/select or drop/i), selectedFile("{"));
    expect(await screen.findByRole("alert")).toHaveTextContent("valid JSON");
    await user.upload(screen.getByLabelText(/select or drop/i), selectedFile('{"profile":{}}'));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("OSCAL Catalog"));
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
