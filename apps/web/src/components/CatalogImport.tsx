// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent } from "react";

import { bffGet } from "@/lib/bff-client";
import { ApiError, ERROR_MESSAGES, kindForStatus } from "@/lib/errors";
import { useI18n } from "@/lib/i18n/provider";
import type { Translate } from "@/lib/i18n";
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

async function importError(
  response: Response,
  t: Translate,
  errorMessage: (error: unknown) => string,
): Promise<string> {
  if (response.status === 413) return t("catalogs.fileExceedsConfiguredLimit");
  if (response.status >= 500) return t("catalogs.importMayHaveCompleted");
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
  const kind = kindForStatus(response.status);
  return errorMessage(new ApiError(kind, response.status, ERROR_MESSAGES[kind]));
}

export function CatalogImport({ tenantId }: { tenantId: string }) {
  const { t, number, date, errorMessage } = useI18n();
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
      setError(t("catalogs.fileMustBeJson"));
      return;
    }
    if (selected.size > MAX_FILE_BYTES) {
      setError(t("catalogs.fileExceedsUploadLimit"));
      return;
    }
    setReading(true);
    try {
      const parsed: unknown = JSON.parse(await selected.text());
      if (sequence !== currentFile.current) return;
      const catalog = object(object(parsed)?.catalog);
      if (!catalog) {
        setError(t("catalogs.invalidCatalogDocument"));
        return;
      }
      setPreview(catalog);
    } catch {
      if (sequence === currentFile.current) setError(t("catalogs.invalidJson"));
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
      setError(errorMessage(cause));
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
        setError(await importError(response, t, errorMessage));
        return;
      }
      setResult(await response.json() as ImportResult);
      router.replace(`/t/${tenantId}/catalogs`, { scroll: false });
      router.refresh();
    } catch {
      setError(t("catalogs.importMayHaveCompleted"));
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }

  const metadata = object(preview?.metadata);
  const fields: [string, string | null][] = [
    [t("catalogs.title"), text(metadata?.title)],
    [t("catalogs.catalogUuid"), text(preview?.uuid)],
    [t("catalogs.catalogVersionField"), text(metadata?.version)],
    [t("catalogs.oscalSpecVersionField"), text(metadata?.["oscal-version"])],
    [t("catalogs.lastModified"), text(metadata?.["last-modified"])],
  ];

  if (!open) return <button type="button" onClick={() => setOpen(true)}>{t("catalogs.import")}</button>;

  return (
    <section className="panel catalog-import" aria-labelledby="import-heading">
      <h2 id="import-heading">{t("catalogs.import")}</h2>
      {result ? (
        <div role="status">
          <p>{result.created ? t("catalogs.importComplete") : t("catalogs.documentExists")}</p>
          <p>{result.catalog_name} · {t("catalogs.revision", { name: number(result.revision_number) })} · {result.control_count === 1
            ? t("catalogs.controlsCountOne", { name: number(result.control_count) })
            : t("catalogs.controlsCountOther", { name: number(result.control_count) })}</p>
          <p>{t("catalogs.catalogVersion")}: {result.source_version ?? t("catalogs.notRecorded")} · {t("catalogs.oscalSpecificationVersion")}: {result.oscal_version}</p>
          <a href={`/t/${tenantId}/catalogs/${result.catalog_id}?revision=${result.revision_id}`}>{t("catalogs.openImportedRevision")}</a>
          {" "}<button className="secondary" type="button" onClick={() => { setOpen(false); setResult(null); void selectFile(null); }}>{t("catalogs.close")}</button>
        </div>
      ) : (
        <form onSubmit={submit} className="profile-form">
          <p>{t("catalogs.uploadInstructions")}</p>
          <div className="empty" onDragOver={(event) => event.preventDefault()} onDrop={(event) => {
            event.preventDefault();
            if (!busy) void selectFile(event.dataTransfer.files[0] ?? null);
          }}>
            <label htmlFor="catalog-file">{t("catalogs.selectOrDropJson")}</label>{" "}
            <input id="catalog-file" type="file" accept=".json,application/json" disabled={busy}
              onChange={(event) => { void selectFile(event.target.files?.[0] ?? null); event.target.value = ""; }} />
          </div>
          {file ? <p>{file.name} ({number(file.size)} {t("catalogs.bytes")}){" "}
            <button type="button" className="secondary" disabled={busy} onClick={() => void selectFile(null)}>{t("catalogs.removeFile")}</button></p> : null}
          {reading ? <p>{t("catalogs.readingFile")}</p> : null}
          {preview ? <dl className="meta-list">{fields.filter(([, value]) => value).map(([label, value]) => (
            <div key={label} className="import-meta-row"><dt>{label}</dt><dd>{label === t("catalogs.lastModified") && value ? date(value) : value}</dd></div>
          ))}</dl> : null}
          <fieldset disabled={busy}>
            <legend>{t("catalogs.importDestination")}</legend>
            <label><input type="radio" name="destination" checked={mode === "new"} onChange={() => setMode("new")} /> {t("catalogs.newCatalog")}</label>{" "}
            <label><input type="radio" name="destination" checked={mode === "existing"} onChange={() => {
              setMode("existing");
              if (!catalogs) void loadCatalogs("");
            }} /> {t("catalogs.newRevisionExisting")}</label>
            <p className="muted">{t("catalogs.newCatalogSeparate")}</p>
            {mode === "existing" ? <>
              <div className="search-form">
                <div className="field"><label htmlFor="target-search">{t("catalogs.findCatalog")}</label>
                  <input id="target-search" type="search" value={search} maxLength={200} onChange={(event) => setSearch(event.target.value)} /></div>
                <button type="button" className="secondary" disabled={loadingCatalogs} onClick={() => void loadCatalogs(search)}>{t("catalogs.search")}</button>
              </div>
              {loadingCatalogs ? <p>{t("catalogs.loading")}</p> : null}
              {catalogs ? <>
                <div className="field"><label htmlFor="target-catalog">{t("catalogs.targetCatalog")}</label>
                  <select id="target-catalog" value={target} onChange={(event) => setTarget(event.target.value)}>
                    <option value="">{t("catalogs.selectCatalog")}</option>
                    {target && !catalogs.items.some((item) => item.id === target) ? <option value={target}>{target} ({t("catalogs.selected")})</option> : null}
                    {catalogs.items.map((item) => <option key={item.id} value={item.id}>{item.name} ({item.id})</option>)}
                  </select>
                </div>
                <p>{catalogs.total === 1
                  ? t("catalogs.catalogsFoundOne", { name: number(catalogs.total) })
                  : t("catalogs.catalogsFoundOther", { name: number(catalogs.total) })}{" "}
                  {catalogs.offset > 0 ? <button type="button" className="secondary" disabled={loadingCatalogs} onClick={() => void loadCatalogs(loadedSearch, Math.max(0, catalogs.offset - catalogs.limit))}>{t("catalogs.previous")}</button> : null}{" "}
                  {catalogs.offset + catalogs.limit < catalogs.total ? <button type="button" className="secondary" disabled={loadingCatalogs} onClick={() => void loadCatalogs(loadedSearch, catalogs.offset + catalogs.limit)}>{t("catalogs.next")}</button> : null}</p>
              </> : null}
            </> : null}
          </fieldset>
          {error ? <div role="alert" className="alert" style={{ whiteSpace: "pre-wrap" }}>{error}</div> : null}
          <div className="workspace-actions">
            <button type="submit" disabled={!preview || reading || busy || (mode === "existing" && !target)}>{busy ? t("catalogs.importing") : t("catalogs.import")}</button>
            <button type="button" className="secondary" disabled={busy} onClick={() => setOpen(false)}>{t("catalogs.cancel")}</button>
          </div>
        </form>
      )}
    </section>
  );
}
