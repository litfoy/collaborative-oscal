"use client";

import { useState, type FormEvent } from "react";

import { bffWrite } from "@/lib/bff-client";
import { ApiError, ERROR_MESSAGES } from "@/lib/errors";
import type { Catalog, Profile } from "@/lib/types";

function parseControlIds(value: string): string[] {
  return [...new Set(value.split(/[\n,]/).map((id) => id.trim()).filter(Boolean))];
}

export function ProfileManager({
  tenantId,
  profiles: initialProfiles,
  catalogs,
  canWrite,
}: {
  tenantId: string;
  profiles: Profile[];
  catalogs: Catalog[];
  canWrite: boolean;
}) {
  const [profiles, setProfiles] = useState(initialProfiles);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState("");
  const [selection, setSelection] = useState("");
  const [catalogId, setCatalogId] = useState(
    catalogs.find((catalog) => catalog.latest_revision)?.id ?? "",
  );

  const create = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const catalog = catalogs.find((item) => item.id === catalogId);
    if (!catalog?.latest_revision) {
      setError("Choose a catalog with an available revision.");
      return;
    }
    const controlIds = parseControlIds(selection);
    if (controlIds.length === 0) {
      setError("Enter at least one OSCAL control ID.");
      return;
    }
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      const created = await bffWrite<Profile>("POST", `tenants/${tenantId}/profiles`, {
        catalog_id: catalog.id,
        revision_id: catalog.latest_revision.id,
        title,
        control_ids: controlIds,
      });
      setProfiles((current) => [created, ...current]);
      setTitle("");
      setSelection("");
      setStatus(`Profile “${created.title}” created.`);
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  };

  const save = async (updated: Profile) => {
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      const saved = await bffWrite<Profile>(
        "PUT",
        `tenants/${tenantId}/profiles/${updated.id}`,
        { title: updated.title, control_ids: updated.control_ids },
      );
      setProfiles((current) => current.map((item) => (item.id === saved.id ? saved : item)));
      setStatus(`Profile “${saved.title}” saved.`);
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="profile-manager">
      {error ? <p role="alert" className="alert">{error}</p> : null}
      {status ? <p role="status">{status}</p> : null}

      {canWrite ? (
        <section className="panel" aria-labelledby="create-profile-heading">
          <h2 id="create-profile-heading">Create profile</h2>
          {catalogs.some((catalog) => catalog.latest_revision) ? (
            <form className="profile-form" onSubmit={create}>
              <label className="field">
                Profile title
                <input
                  required
                  maxLength={255}
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                />
              </label>
              <label className="field">
                Source catalog and latest revision
                <select
                  value={catalogId}
                  onChange={(event) => setCatalogId(event.target.value)}
                >
                  {catalogs.filter((item) => item.latest_revision).map((catalog) => (
                    <option key={catalog.id} value={catalog.id}>
                      {catalog.name} — revision {catalog.latest_revision?.revision_number}
                    </option>
                  ))}
                </select>
              </label>
              <ControlIdsField value={selection} onChange={setSelection} />
              <button type="submit" disabled={busy}>
                Create profile
              </button>
            </form>
          ) : (
            <p className="muted">Import a catalog before creating a profile.</p>
          )}
        </section>
      ) : (
        <p className="muted">You need the catalog:write permission to create or edit profiles.</p>
      )}

      <h2>Existing profiles</h2>
      {profiles.length === 0 ? (
        <div className="empty">No profiles have been created in this workspace.</div>
      ) : (
        <ul className="profile-list">
          {profiles.map((profile) => {
            const catalog = catalogs.find((item) => item.id === profile.catalog_id);
            return (
              <li className="panel" key={profile.id}>
                {canWrite ? (
                  <ProfileEditForm profile={profile} busy={busy} onSave={save} />
                ) : (
                  <>
                    <h3>{profile.title}</h3>
                    <p>{profile.control_ids.join(", ")}</p>
                  </>
                )}
                <p className="muted">
                  Source:{" "}
                  <a
                    href={`/t/${tenantId}/catalogs/${profile.catalog_id}?revision=${profile.revision_id}`}
                  >
                    {catalog?.name ?? "Catalog"} · selected revision
                  </a>
                </p>
                <a href={`/bff/tenants/${tenantId}/profiles/${profile.id}/export`}>
                  Export OSCAL JSON
                </a>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function ProfileEditForm({
  profile,
  busy,
  onSave,
}: {
  profile: Profile;
  busy: boolean;
  onSave: (profile: Profile) => Promise<void>;
}) {
  const [title, setTitle] = useState(profile.title);
  const [controlIds, setControlIds] = useState(profile.control_ids.join("\n"));
  return (
    <form
      className="profile-form"
      onSubmit={(event) => {
        event.preventDefault();
        void onSave({ ...profile, title: title.trim(), control_ids: parseControlIds(controlIds) });
      }}
    >
      <label className="field">
        Profile title
        <input
          required
          maxLength={255}
          value={title}
          onChange={(event) => setTitle(event.target.value)}
        />
      </label>
      <ControlIdsField value={controlIds} onChange={setControlIds} />
      <button type="submit" disabled={busy || parseControlIds(controlIds).length === 0}>
        Save profile
      </button>
    </form>
  );
}

function ControlIdsField({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="field">
      Selected OSCAL control IDs
      <textarea
        required
        rows={4}
        placeholder={"ac-1\nac-2"}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      <span className="muted">Enter one ID per line or separate IDs with commas.</span>
    </label>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError) return cause.message;
  return ERROR_MESSAGES.unavailable;
}
