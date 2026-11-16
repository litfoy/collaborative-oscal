import { redirect } from "next/navigation";

import { ApiProblem } from "@/components/ApiProblem";
import { AppShell } from "@/components/AppShell";
import { LanguageSelector } from "@/components/LanguageSelector";
import { listTenants } from "@/lib/api";
import { getSession } from "@/lib/auth";
import { safeReturnTo } from "@/lib/safe";
import type { TranslationKey } from "@/lib/i18n";
import { getI18n } from "@/lib/i18n/server";

const NOTICES: Record<string, TranslationKey> = {
  expired: "auth.expiredNotice",
  login_failed: "auth.loginFailed",
  provider_unavailable: "auth.providerUnavailable",
};

export default async function HomePage({
  searchParams,
}: {
  searchParams: Promise<{ reason?: string; error?: string; returnTo?: string }>;
}) {
  const { t, enumLabel } = await getI18n();
  const params = await searchParams;
  const session = await getSession();

  if (!session) {
    const notice = NOTICES[params.reason ?? params.error ?? ""];
    const returnTo = safeReturnTo(params.returnTo);
    return (
      <>
      <header className="shell-header"><span className="brand">Collaborative OSCAL</span><LanguageSelector /></header>
      <main id="main" className="page page-narrow">
        <div className="panel">
          <h1>Collaborative OSCAL</h1>
          <p className="muted">{t("auth.intro")}</p>
          {notice ? (
            <p role="alert" className="alert">
              {t(notice)}
            </p>
          ) : null}
          <a className="button" href={`/auth/login?returnTo=${encodeURIComponent(returnTo)}`}>
            {t("auth.signIn")}
          </a>
        </div>
      </main>
      </>
    );
  }

  let tenants;
  try {
    tenants = (await listTenants("/")).items;
  } catch (error) {
    return (
      <AppShell userName={session.name ?? session.email ?? t("auth.signedIn")} tenants={[]} demoMode={"kind" in session && session.kind === "demo"}>
        <ApiProblem error={error} />
      </AppShell>
    );
  }

  if (tenants.length === 1) {
    redirect(`/t/${tenants[0].id}/catalogs`);
  }

  return (
    <AppShell userName={session.name ?? session.email ?? t("auth.signedIn")} tenants={tenants} demoMode={"kind" in session && session.kind === "demo"}>
      <h1>{t("auth.chooseWorkspace")}</h1>
      {tenants.length === 0 ? (
        <div className="empty">
          <p>{t("auth.noWorkspace")}</p>
          <p>{t("auth.askAdmin")}</p>
        </div>
      ) : (
        <ul className="card-grid">
          {tenants.map((tenant) => (
            <li key={tenant.id} className="card">
              <h2>
                <a href={`/t/${tenant.id}/catalogs`}>{tenant.name}</a>
              </h2>
              <p className="muted">{t("auth.yourRole")} {enumLabel(tenant.role)}</p>
            </li>
          ))}
        </ul>
      )}
    </AppShell>
  );
}
