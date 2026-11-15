import Link from "next/link";
import type { ReactNode } from "react";

import type { Tenant } from "@/lib/types";

export function AppShell({
  userName,
  tenants,
  currentTenantId,
  demoMode = false,
  children,
}: {
  userName: string;
  tenants: Tenant[];
  currentTenantId?: string;
  demoMode?: boolean;
  children: ReactNode;
}) {
  const current = tenants.find((tenant) => tenant.id === currentTenantId);
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to main content
      </a>
      <header className="shell-header">
        <nav aria-label="Primary">
          <Link className="brand" href="/">
            Collaborative OSCAL
          </Link>
          {current ? (
            <>
              <a href={`/t/${current.id}/catalogs`}>Catalogs</a>
              <a href={`/t/${current.id}/measures`}>Our Measures &amp; Controls</a>
              <a href={`/t/${current.id}/mappings`}>Control mappings</a>
              <a href={`/t/${current.id}/profiles`}>Profiles</a>
              <a href={`/t/${current.id}/systems`}>Systems and SSPs</a>
              <span className="muted">Workspace: {current.name}</span>
              {tenants.length > 1 ? <Link href="/">Switch workspace</Link> : null}
            </>
          ) : null}
        </nav>
        <div className="shell-user">
          {demoMode ? <strong>Demo Mode</strong> : null}
          <span>{userName}</span>
          {!demoMode ? (
          <form action="/auth/logout" method="post">
            <button type="submit" className="secondary">
              Sign out
            </button>
          </form>
          ) : null}
        </div>
      </header>
      <main id="main" className="page">
        {children}
      </main>
    </>
  );
}
