"use client";

import { useState, type FormEvent } from "react";

import type { InformationSystem } from "@/lib/types";

export function SystemsList({
  tenantId,
  initialSystems,
  initialCounts,
  canWrite,
}: {
  tenantId: string;
  initialSystems: InformationSystem[];
  initialCounts: Record<string, { components: number; plans: number }>;
  canWrite: boolean;
}) {
  const [systems, setSystems] = useState(initialSystems);
  const [counts, setCounts] = useState(initialCounts);
  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const visibleSystems = systems.filter((system) => system.name.toLowerCase().includes(query.trim().toLowerCase()));

  async function createSystem(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch(`/bff/tenants/${tenantId}/systems`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          description: null,
          system_boundary: null,
          system_ids: [],
          information_types: [],
          operational_status: null,
          status_remarks: null,
          security_sensitivity_level: null,
          organization_id: null,
        }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(readError(result));
      setSystems((current) => [result as InformationSystem, ...current]);
      setCounts((current) => ({ ...current, [result.id]: { components: 0, plans: 0 } }));
      setName("");
      setQuery("");
      setCreating(false);
      setNotice("System created.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The System could not be created.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="workspace">
      {notice ? <p role="status">{notice}</p> : null}
      {!creating ? <div className="workspace-actions workspace-heading">
        <label className="field">
          Search systems
          <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} />
        </label>
        {canWrite ? <button type="button" onClick={() => setCreating(true)}>New system</button> : null}
      </div> : null}
      {canWrite && creating ? (
        <form className="panel search-form" onSubmit={createSystem}>
          <label className="field">
            System name
            <input
              required
              maxLength={255}
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Corporate Identity Management"
            />
          </label>
          <button type="submit" disabled={busy || !name.trim()}>
            {busy ? "Creating…" : "Create system"}
          </button>
          <button type="button" className="secondary" onClick={() => setCreating(false)}>Close</button>
          {error ? <p role="alert">{error}</p> : null}
        </form>
      ) : !canWrite ? (
        <p className="muted">You need catalog:write permission to create or edit Systems.</p>
      ) : null}
      {!creating && systems.length === 0 ? (
        <div className="empty">No Systems have been created in this workspace.</div>
      ) : !creating && visibleSystems.length === 0 ? (
        <div className="empty">No systems match your search.</div>
      ) : !creating ? (
        <ul className="profile-list">
          {visibleSystems.map((system) => (
            <li className="panel" key={system.id}>
              <h3>{system.name}</h3>
              <p className="muted">
                {system.operational_status ?? "Operational status not set"} ·{" "}
                {counts[system.id]?.components} components · {counts[system.id]?.plans} SSPs
              </p>
              <a className="button" href={`/t/${tenantId}/systems/${system.id}`}>
                Open System
              </a>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function readError(body: unknown): string {
  if (typeof body === "object" && body !== null && "detail" in body) {
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (typeof detail === "object" && detail !== null && "diagnostics" in detail) {
      const diagnostics = (detail as { diagnostics?: { message?: string }[] }).diagnostics;
      if (diagnostics?.length) return diagnostics.map((item) => item.message).join(" ");
    }
  }
  return "The request could not be completed.";
}
