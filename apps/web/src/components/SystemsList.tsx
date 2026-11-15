"use client";

import { useState, type FormEvent } from "react";

import type { InformationSystem } from "@/lib/types";

export function SystemsList({
  tenantId,
  initialSystems,
  canWrite,
}: {
  tenantId: string;
  initialSystems: InformationSystem[];
  canWrite: boolean;
}) {
  const [systems, setSystems] = useState(initialSystems);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function createSystem(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
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
      setName("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The System could not be created.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="workspace">
      {canWrite ? (
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
            {busy ? "Creating…" : "Create System"}
          </button>
          {error ? <p role="alert">{error}</p> : null}
        </form>
      ) : (
        <p className="muted">You need catalog:write permission to create or edit Systems.</p>
      )}
      <h2>Systems</h2>
      {systems.length === 0 ? (
        <div className="empty">No Systems have been created in this workspace.</div>
      ) : (
        <ul className="profile-list">
          {systems.map((system) => (
            <li className="panel" key={system.id}>
              <h3>{system.name}</h3>
              <p>{system.description || "System characteristics are incomplete."}</p>
              <p className="muted">
                {system.system_ids.length} system identifiers · {system.information_types.length}{" "}
                information types · {system.operational_status ?? "operational status not set"}
              </p>
              <a className="button" href={`/t/${tenantId}/systems/${system.id}`}>
                Open System
              </a>
            </li>
          ))}
        </ul>
      )}
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
