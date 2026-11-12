"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent } from "react";

import { bffGet } from "@/lib/bff-client";
import { ApiError, ERROR_MESSAGES, kindForStatus } from "@/lib/errors";
import type { Catalog, Paged } from "@/lib/types";

const MAX_FILE_BYTES = 100 * 1024 * 1024;

interface ImportResult {
  catalog_id: string;
  catalog_name: string;
  revision_id: string;
  revision_number: number;
  oscal_document_uuid: string;
  oscal_version: string;
  source_version: string | null;
  control_count: number;
  created: boolean;
}

function object(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

async function importError(response: Response): Promise<string> {
  if (response.status === 413) return "The file exceeds the configured upload size limit.";
  if (response.status >= 500) return "The import may have completed. Check the Catalogs list before retrying.";
  try {
    const body = object(await response.json());
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    const problem = object(detail);
    if (Array.isArray(problem?.errors)) {
      const messages = problem.errors.flatMap((item: unknown) => {
        const issue = object(item);
        const message = text(issue?.message);
        const path = text(issue?.path);
        return message ? [`${message}${path ? ` (${path})` : ""}`] : [];
      });
      if (messages.length) return messages.join("\n");
    }
  } catch {
    // Use the status-based message for non-JSON responses.
  }
  return ERROR_MESSAGES[kindForStatus(response.status)];
}

export function CatalogImport({ tenantId }: { tenantId: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");
  const [reading, setReading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [mode, setMode] = useState<"new" | "existing">("new");
  const [target, setTarget] = useState("");
  const [search, setSearch] = useState("");
  const [loadedSearch, setLoadedSearch] = useState("");
  const [catalogs, setCatalogs] = useState<Paged<Catalog> | null>(null);
  const [loadingCatalogs, setLoadingCatalogs] = useState(false);
  const currentFile = useRef(0);
  const submitting = useRef(false);

  async function selectFile(selected: File | null) {
    const sequence = ++currentFile.current;
    setFile(selected);
    setPreview(null);
    setError("");
    setResult(null);
    setReading(false);
    if (!selected) return;
    if (!selected.name.toLowerCase().endsWith(".json")) {
      setError("Select an OSCAL Catalog JSON file.");
      return;
    }
    if (selected.size > MAX_FILE_BYTES) {
      setError("The file exceeds the maximum upload size of 100 MiB.");
      return;
    }
    setReading(true);
    try {
      const parsed: unknown = JSON.parse(await selected.text());
      if (sequence !== currentFile.current) return;
      const catalog = object(object(parsed)?.catalog);
      if (!catalog) {
        setError("The document does not contain an OSCAL Catalog object.");
        return;
      }
      setPreview(catalog);
    } catch {
      if (sequence === currentFile.current) setError("The file could not be read as valid JSON.");
    } finally {
      if (sequence === currentFile.current) setReading(false);
    }
  }

  async function loadCatalogs(query: string, offset = 0) {
    setLoadingCatalogs(true);
    setError("");
    try {
      setCatalogs(await bffGet<Paged<Catalog>>(`tenants/${tenantId}/catalogs`, { q: query, offset }));
      setLoadedSearch(query);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : ERROR_MESSAGES.unavailable);
    } finally {
      setLoadingCatalogs(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (submitting.current || !file || !preview || (mode === "existing" && !target)) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    try {
      const path = mode === "new" ? "import" : `${target}/import`;
      const response = await fetch(`/bff/tenants/${tenantId}/catalogs/${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        credentials: "same-origin",
        body: file,
      });
      if (!response.ok) {
        setError(await importError(response));
        return;
      }
      setResult(await response.json() as ImportResult);
      router.replace(`/t/${tenantId}/catalogs`, { scroll: false });
      router.refresh();
    } catch {
      setError("The import may have completed. Check the Catalogs list before retrying.");
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }

  const metadata = object(preview?.metadata);
  const fields: [string, string | null][] = [
    ["Title", text(metadata?.title)],
    ["Catalog UUID", text(preview?.uuid)],
    ["Catalog version", text(metadata?.version)],
    ["OSCAL specification version", text(metadata?.["oscal-version"])],
    ["Last modified", text(metadata?.["last-modified"])],
  ];

  if (!open) return <button type="button" onClick={() => setOpen(true)}>Import catalog</button>;

  return (
    <section className="panel catalog-import" aria-labelledby="import-heading">
      <h2 id="import-heading">Import catalog</h2>
      {result ? (
        <div role="status">
          <p>{result.created ? "Import complete." : "This document already exists in the selected catalog."}</p>
          <p>{result.catalog_name} · Revision {result.revision_number} · {result.control_count} controls</p>
          <p>Catalog version: {result.source_version ?? "Not recorded"} · OSCAL specification version: {result.oscal_version}</p>
          <a href={`/t/${tenantId}/catalogs/${result.catalog_id}?revision=${result.revision_id}`}>Open imported revision</a>
          {" "}<button className="secondary" type="button" onClick={() => { setOpen(false); setResult(null); void selectFile(null); }}>Close</button>
        </div>
      ) : (
        <form onSubmit={submit} className="profile-form">
          <p>Upload an OSCAL Catalog JSON file. The server validates OSCAL 1.1.3 and 1.2.1.</p>
          <div className="empty" onDragOver={(event) => event.preventDefault()} onDrop={(event) => {
            event.preventDefault();
            if (!busy) void selectFile(event.dataTransfer.files[0] ?? null);
          }}>
            <label htmlFor="catalog-file">Select or drop a JSON file</label>{" "}
            <input id="catalog-file" type="file" accept=".json,application/json" disabled={busy}
              onChange={(event) => { void selectFile(event.target.files?.[0] ?? null); event.target.value = ""; }} />
          </div>
          {file ? <p>{file.name} ({file.size.toLocaleString()} bytes){" "}
            <button type="button" className="secondary" disabled={busy} onClick={() => void selectFile(null)}>Remove file</button></p> : null}
          {reading ? <p>Reading file…</p> : null}
          {preview ? <dl className="meta-list">{fields.filter(([, value]) => value).map(([label, value]) => (
            <div key={label} className="import-meta-row"><dt>{label}</dt><dd>{value}</dd></div>
          ))}</dl> : null}
          <fieldset disabled={busy}>
            <legend>Import destination</legend>
            <label><input type="radio" name="destination" checked={mode === "new"} onChange={() => setMode("new")} /> New catalog</label>{" "}
            <label><input type="radio" name="destination" checked={mode === "existing"} onChange={() => {
              setMode("existing");
              if (!catalogs) void loadCatalogs("");
            }} /> New revision of an existing catalog</label>
            <p className="muted">A new catalog is separate even if its document was imported before. Choose an existing catalog to detect duplicates within it. Existing references remain on their original revisions.</p>
            {mode === "existing" ? <>
              <div className="search-form">
                <div className="field"><label htmlFor="target-search">Find a catalog</label>
                  <input id="target-search" type="search" value={search} maxLength={200} onChange={(event) => setSearch(event.target.value)} /></div>
                <button type="button" className="secondary" disabled={loadingCatalogs} onClick={() => void loadCatalogs(search)}>Search</button>
              </div>
              {loadingCatalogs ? <p>Loading catalogs…</p> : null}
              {catalogs ? <>
                <div className="field"><label htmlFor="target-catalog">Target catalog</label>
                  <select id="target-catalog" value={target} onChange={(event) => setTarget(event.target.value)}>
                    <option value="">Select a catalog</option>
                    {target && !catalogs.items.some((item) => item.id === target) ? <option value={target}>{target} (selected)</option> : null}
                    {catalogs.items.map((item) => <option key={item.id} value={item.id}>{item.name} ({item.id})</option>)}
                  </select>
                </div>
                <p>{catalogs.total} catalogs found.{" "}
                  {catalogs.offset > 0 ? <button type="button" className="secondary" disabled={loadingCatalogs} onClick={() => void loadCatalogs(loadedSearch, Math.max(0, catalogs.offset - catalogs.limit))}>Previous</button> : null}{" "}
                  {catalogs.offset + catalogs.limit < catalogs.total ? <button type="button" className="secondary" disabled={loadingCatalogs} onClick={() => void loadCatalogs(loadedSearch, catalogs.offset + catalogs.limit)}>Next</button> : null}</p>
              </> : null}
            </> : null}
          </fieldset>
          {error ? <div role="alert" className="alert" style={{ whiteSpace: "pre-wrap" }}>{error}</div> : null}
          <div className="workspace-actions">
            <button type="submit" disabled={!preview || reading || busy || (mode === "existing" && !target)}>{busy ? "Importing…" : "Import catalog"}</button>
            <button type="button" className="secondary" disabled={busy} onClick={() => setOpen(false)}>Cancel</button>
          </div>
        </form>
      )}
    </section>
  );
}
