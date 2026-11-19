// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

"use client";

import { useState } from "react";

import { useI18n } from "@/lib/i18n/provider";
import type { Catalog, Profile } from "@/lib/types";

import { ProfileWorkspace } from "./ProfileWorkspace";

export function ProfileManager({
  tenantId, profiles: initialProfiles, catalogs, catalogTotal = catalogs.length, canWrite,
}: {
  tenantId: string;
  profiles: Profile[];
  catalogs: Catalog[];
  catalogTotal?: number;
  canWrite: boolean;
}) {
  const { t, number, date } = useI18n();
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
        catalogName={catalogs.find((item) => item.id === workspace.profile.catalog_id)?.name ?? t("profiles.catalogFallback")}
        catalogs={catalogs}
        catalogTotal={catalogTotal}
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
                control_ids: [], created_at: "", updated_at: "", concurrency_version: 1,
            },
          });
        }}>
          <label className="field">
            {t("profiles.sourceCatalogRevision")}
            <select value={catalogId} onChange={(event) => setCatalogId(event.target.value)}>
              {available.map((catalog) => (
                <option key={catalog.id} value={catalog.id}>
                  {catalog.name} — {t("profiles.revision", { name: number(catalog.latest_revision?.revision_number ?? 0) })}
                </option>
              ))}
            </select>
          </label>
          <button type="submit">{t("profiles.create")}</button>
        </form>
      ) : <p className="muted">{canWrite ? t("profiles.importBeforeCreate") : t("profiles.permissionRequired")}</p>}

      <h2>{t("profiles.existing")}</h2>
      {profiles.length === 0 ? <div className="empty">{t("profiles.none")}</div> : (
        <ul className="profile-list">
          {profiles.map((profile) => (
            <li className="panel" key={profile.id}>
              <h3>{profile.title}</h3>
              {profile.description ? <p className="prose">{profile.description}</p> : null}
              {(profile.imports ?? [profile]).map((source) => <p key={source.id}>
                <a href={`/t/${tenantId}/catalogs/${source.catalog_id}?revision=${source.revision_id}`}>
                  {catalogs.find((item) => item.id === source.catalog_id)?.name ?? t("profiles.catalogFallback")}
                </a>{" · "}{source.control_ids.length === 1
                  ? t("profiles.selectedRequirementsCountOne", { name: number(source.control_ids.length) })
                  : t("profiles.selectedRequirementsCountOther", { name: number(source.control_ids.length) })} · {t("profiles.pinnedRevision")} <span className="mono">{source.revision_id}</span>
              </p>)}
              <p className="muted">{t("profiles.lastModified")}: <time dateTime={profile.updated_at}>{date(profile.updated_at)}</time></p>
              <div className="workspace-actions">
                <button type="button" onClick={() => setWorkspace({ profile, isNew: false })}>
                  {canWrite ? t("profiles.edit") : t("profiles.view")}
                </button>
                <a className="button secondary" href={`/bff/tenants/${tenantId}/profiles/${profile.id}/export`}>{t("profiles.export")}</a>
                {canWrite ? <button className="secondary" type="button" onClick={() => setWorkspace({
                  isNew: true, profile: { ...profile, id: "new", title: `${profile.title} (copy)`.slice(0, 255),
                    imports: profile.imports?.map((item) => ({ ...item, id: crypto.randomUUID() })), concurrency_version: 1 },
                })}>{t("profiles.duplicate")}</button> : null}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
