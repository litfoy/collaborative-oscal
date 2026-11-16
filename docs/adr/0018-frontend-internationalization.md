# ADR 0018: Interface localization independent of OSCAL content

## Status

Accepted

## Decision

Support English (`en`, the default) and German (`de`) without locale-prefixed
routes, backend changes, or additional dependencies. The header language selector
stores a non-sensitive, host-only `co_locale` cookie for one year, with `Path=/`
and `SameSite=Lax` (`Secure` on HTTPS). It is deliberately readable by the browser
and independent of authentication, tenant membership, and authorization.
Unsupported or missing locale values resolve to English.

The root Server Component reads the cookie using Next.js `cookies()`, sets
`html.lang`, and initializes a client locale provider before hydration.
Server pages use `getI18n()`; Client Components use `useI18n()`. Switching updates
the provider and cookie, then refreshes the current Server Component tree without
changing the URL. Existing client component instances and their form state are
preserved where React reconciliation permits. No document mutation is requested
by switching languages.

Typed, flat dictionaries live in `apps/web/src/lib/i18n/`, grouped into common,
catalog/profile, measure/mapping/register, and system/SSP resources. Keys identify
the functional area and meaning, not English sentences. German resources must
implement all English keys; runtime lookup also falls back to English.
`Intl.NumberFormat` and `Intl.DateTimeFormat` handle presentation; timestamps use
UTC consistently on server and browser to avoid hydration discrepancies.
Singular/plural messages use separate keys selected by the actual count.

Translate only interface text and enumeration display labels. Source document
titles, statements, metadata, property labels, user-authored text, identifiers,
stored enumeration values, JSON keys, API payloads, and exports remain unchanged.
Mapping relationship identifiers stay accessible alongside their display labels.
Locale is not an input to document digests, UUIDs, revisions, or SSP snapshots.

Known API error kinds are localized in the frontend. Backend validation messages
without a stable translatable code remain verbatim with localized context;
paths, identifiers, codes, and diagnostic details are not hidden. Do not infer
translations by parsing English diagnostic prose.

## Consequences

Both languages ship in the same web image and require no environment settings,
database storage, or new Docker services. English remains available when a
translation is missing. New interfaces, including future Assessment Plans,
Assessment Results, and POA&M workspaces, must use these same resources.

The implementation intentionally provides only dictionary lookup, named
interpolation, enum display labels, and native `Intl` formatting, not a
general-purpose internationalization framework. More complex grammatical needs
can justify an established maintained library in a future decision.
