"use client";

import { useState, useSyncExternalStore } from "react";

import type { Catalog, Profile } from "@/lib/types";

import { ProfileWorkspace } from "./ProfileWorkspace";

const subscribe = () => () => {};
const clientSnapshot = () => true;
const serverSnapshot = () => false;

export function ProfileManager({
  tenantId, profiles: initialProfiles, catalogs, canWrite,
}: {
  tenantId: string;
  profiles: Profile[];
  catalogs: Catalog[];
  canWrite: boolean;
}) {
  const hydrated = useSyncExternalStore(subscribe, clientSnapshot, serverSnapshot);
  const [profiles, setProfiles] = useState(initialProfiles);
  const [catalogId, setCatalogId] = useState(catalogs.find((item) => item.latest_revision)?.id ?? "");
  const [workspace, setWorkspace] = useState<{ profile: Profile; isNew: boolean } | null>(null);
  const available = catalogs.filter((item) => item.latest_revision);

  if (workspace) {
    return (
      <ProfileWorkspace
        key={`${workspace.profile.id}:${workspace.isNew}`}
        tenantId={tenantId}
        initialProfile={workspace.profile}
        isNew={workspace.isNew}
        catalogName={catalogs.find((item) => item.id === workspace.profile.catalog_id)?.name ?? "Catalog"}
        canWrite={canWrite}
        onClose={() => setWorkspace(null)}
        onSaved={(saved) => {
          setProfiles((current) => [saved, ...current.filter((item) => item.id !== saved.id)]);
        }}
      />
    );
  }

  return (
    <div className="profile-manager">
      {canWrite && available.length > 0 ? (
        <form className="panel search-form" onSubmit={(event) => {
          event.preventDefault();
          const catalog = available.find((item) => item.id === catalogId);
          if (!catalog?.latest_revision) return;
          setWorkspace({
            isNew: true,
            profile: {
              id: "new", tenant_id: tenantId, catalog_id: catalog.id,
              revision_id: catalog.latest_revision.id, title: "", description: "",
              control_ids: [], created_at: "", updated_at: "",
            },
          });
        }}>
          <label className="field">
            Source catalog and revision for a new profile
            <select value={catalogId} onChange={(event) => setCatalogId(event.target.value)}>
              {available.map((catalog) => (
                <option key={catalog.id} value={catalog.id}>
                  {catalog.name} — revision {catalog.latest_revision?.revision_number}
                </option>
              ))}
            </select>
          </label>
          <button type="submit">Create profile</button>
        </form>
      ) : <p className="muted">{canWrite ? "Import a catalog before creating a profile." : "You need the catalog:write permission to create or edit profiles."}</p>}

      <h2>Existing profiles</h2>
      {profiles.length === 0 ? <div className="empty">No profiles have been created in this workspace.</div> : (
        <ul className="profile-list">
          {profiles.map((profile) => (
            <li className="panel" key={profile.id}>
              <h3>{profile.title}</h3>
              {profile.description ? <p className="prose">{profile.description}</p> : null}
              <p>
                <a href={`/t/${tenantId}/catalogs/${profile.catalog_id}?revision=${profile.revision_id}`}>
                  {catalogs.find((item) => item.id === profile.catalog_id)?.name ?? "Catalog"}
                </a>
                {" · "}{profile.control_ids.length} selected requirements
              </p>
              <p className="muted">Pinned revision: <span className="mono">{profile.revision_id}</span></p>
              <p className="muted">Last modified: <time dateTime={profile.updated_at}>{hydrated
                ? new Date(profile.updated_at).toLocaleString()
                : new Date(profile.updated_at).toISOString().replace("T", " ").replace("Z", " UTC")}</time></p>
              <div className="workspace-actions">
                <button type="button" onClick={() => setWorkspace({ profile, isNew: false })}>
                  {canWrite ? "Edit profile" : "View profile"}
                </button>
                <a className="button secondary" href={`/bff/tenants/${tenantId}/profiles/${profile.id}/export`}>Export OSCAL JSON</a>
                {canWrite ? <button className="secondary" type="button" onClick={() => setWorkspace({
                  isNew: true, profile: { ...profile, id: "new", title: `${profile.title} (copy)`.slice(0, 255) },
                })}>Duplicate</button> : null}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
