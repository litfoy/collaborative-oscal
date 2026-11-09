import { redirect } from "next/navigation";

import { ApiProblem } from "@/components/ApiProblem";
import { AppShell } from "@/components/AppShell";
import { listTenants } from "@/lib/api";
import { getSession } from "@/lib/auth";
import { safeReturnTo } from "@/lib/safe";

const NOTICES: Record<string, string> = {
  expired: "Your session has ended. Please sign in again.",
  login_failed: "Sign-in could not be completed. Please try again.",
  provider_unavailable: "The sign-in service is unavailable. Please try again shortly.",
};

export default async function HomePage({
  searchParams,
}: {
  searchParams: Promise<{ reason?: string; error?: string; returnTo?: string }>;
}) {
  const params = await searchParams;
  const session = await getSession();

  if (!session) {
    const notice = NOTICES[params.reason ?? params.error ?? ""];
    const returnTo = safeReturnTo(params.returnTo);
    return (
      <main id="main" className="page page-narrow">
        <div className="panel">
          <h1>Collaborative OSCAL</h1>
          <p className="muted">Browse your organisation&rsquo;s OSCAL control catalogs.</p>
          {notice ? (
            <p role="alert" className="alert">
              {notice}
            </p>
          ) : null}
          <a className="button" href={`/auth/login?returnTo=${encodeURIComponent(returnTo)}`}>
            Sign in
          </a>
        </div>
      </main>
    );
  }

  let tenants;
  try {
    tenants = (await listTenants("/")).items;
  } catch (error) {
    return (
      <AppShell userName={session.name ?? session.email ?? "Signed in"} tenants={[]}>
        <ApiProblem error={error} />
      </AppShell>
    );
  }

  if (tenants.length === 1) {
    redirect(`/t/${tenants[0].id}/catalogs`);
  }

  return (
    <AppShell userName={session.name ?? session.email ?? "Signed in"} tenants={tenants}>
      <h1>Choose a workspace</h1>
      {tenants.length === 0 ? (
        <div className="empty">
          <p>You do not have access to any workspace yet.</p>
          <p>Ask an administrator to add you to your organisation.</p>
        </div>
      ) : (
        <ul className="card-grid">
          {tenants.map((tenant) => (
            <li key={tenant.id} className="card">
              <h2>
                <a href={`/t/${tenant.id}/catalogs`}>{tenant.name}</a>
              </h2>
              <p className="muted">Your role: {tenant.role.replace("_", " ")}</p>
            </li>
          ))}
        </ul>
      )}
    </AppShell>
  );
}
