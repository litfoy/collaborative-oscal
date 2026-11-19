# Assessment Results REST Import (OSCAL 1.2.1)

## Endpoint

`POST /api/v1/tenants/{tenant_id}/assessment-plans/{plan_id}/versions/{version_id}/assessment-results/import`

- Auth: Bearer token (existing OIDC access-token validation).
- Authorization: tenant membership with `catalog:write`.
- Body: native OSCAL Assessment Results JSON 1.2.1 document (no wrapper envelope).

## Supported OSCAL subset

The import accepts the subset emitted by Assessment Results authoring export draft generation:

- Root: `assessment-results`
- `assessment-results`:
  - `uuid`
  - `metadata` (`title`, `last-modified`, `version`, `oscal-version`)
  - `import-ap.href` (must match the selected Assessment Plan version export URL)
  - `results` (exactly one result entry)
  - optional `back-matter.resources`
- Result entry:
  - `uuid`, `title`, `description`
  - `reviewed-controls.control-selections[0].include-controls[*].control-id`
  - `start` (required timestamp), optional `end`
  - `observations[*]` with `uuid`, `title`, `description`, `methods`, `collected`, optional `subjects`, optional `relevant-evidence`
  - `findings[*]` with `uuid`, `title`, `description`, `target`, optional `related-observations`

Unsupported fields or incompatible values are rejected with `422`; the service does not silently drop content.

## Validation and mapping

The import runs the existing validation stack:

1. Trestle/Pydantic model validation (where configured for version).
2. Official OSCAL schema validation for declared version.
3. Application integrity checks against pinned Assessment Plan context.

Additional import constraints:

- Exactly one `results` entry is required.
- `import-ap.href` must match the selected AP version export path (`_plan_href()` convention).
- Evidence references must use `relevant-evidence.href` fragment links to `back-matter.resources` UUIDs.
- Observation/finding/evidence UUIDs are preserved.

Mapped working-state fields preserve native IDs and values used by existing Assessment Results workspace and publication flow.

## Provenance and identities

On first successful import, the aggregate stores source provenance:

- source OSCAL document UUID (`assessment-results.uuid`)
- source metadata title (`assessment-results.metadata.title`)
- source result UUID (`assessment-results.results[0].uuid`)
- source metadata `version`
- source metadata `last-modified`
- authenticated submitting principal (`user_id`)
- import timestamp (UTC)

Internal aggregate identity remains application-owned (`assessment_results.id`), and publication identity conventions remain unchanged.

## Idempotency and retry semantics

Tenant-scoped submission identity uses source OSCAL document UUID.

- First successful submission: `201` with `AssessmentResultResponse`
- Byte-order/format-insensitive identical replay: `200` with existing resource
- Same source UUID with different content or assessment context: `409` with `detail.code = "import_conflict"`

Content comparison uses canonical JSON digest and is independent of member ordering/formatting.

Concurrent duplicate submissions are protected by database constraints plus transactional conflict handling; replays never overwrite existing edits or published snapshots.

## Error contracts

- `401`: missing/invalid bearer token
- `403`: tenant authorization failure
- `404`: tenant-scoped plan/version not found
- `409`: structured idempotency conflict (`import_conflict`)
- `422`: validation/integrity/import-subset violations with diagnostics

## Reproducible curl example (AI Governance Demo)

```sh
curl -i \
  -X POST "http://127.0.0.1:8000/api/v1/tenants/${TENANT_ID}/assessment-plans/${PLAN_ID}/versions/${PLAN_VERSION_ID}/assessment-results/import" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  --data-binary @- <<JSON
{
  "assessment-results": {
    "uuid": "b2a95d64-00f1-4af8-a4d2-57f9f4c2038a",
    "metadata": {
      "title": "AI Governance Demo automated evidence run",
      "last-modified": "2026-11-19T10:00:00+00:00",
      "version": "automation-run-1",
      "oscal-version": "1.2.1"
    },
    "import-ap": {
      "href": "/api/v1/tenants/${TENANT_ID}/assessment-plans/${PLAN_ID}/versions/${PLAN_VERSION_ID}/export"
    },
    "results": [
      {
        "uuid": "1cc26d6c-412d-47db-adca-f8f4518130ef",
        "title": "Automated assessment result",
        "description": "Automated MFA checks over privileged access controls.",
        "reviewed-controls": {
          "control-selections": [
            {
              "include-controls": [
                {
                  "control-id": "MG-2.2-006"
                }
              ]
            }
          ]
        },
        "start": "2026-11-19T09:00:00+00:00",
        "end": "2026-11-19T09:45:00+00:00",
        "observations": [
          {
            "uuid": "57612a85-4e1b-47fb-bd3c-8090fd17ec36",
            "title": "Model version lineage evidence captured",
            "description": "Automation verified production inference logs include model-version, registry digest, and deployment release references for each scoring event.",
            "methods": [
              "EXAMINE",
              "TEST"
            ],
            "collected": "2026-11-19T09:30:00+00:00",
            "relevant-evidence": [
              {
                "href": "#7bd39e11-3e12-49f8-805d-31189a91ee3f",
                "description": "Automated model lineage telemetry extract"
              }
            ]
          }
        ],
        "findings": [
          {
            "uuid": "e99d6f4c-c48b-4f59-89b7-e8389da53f63",
            "title": "Model version traceability objective satisfied",
            "description": "Evidence confirms each scored request can be traced to the deployed model version and release artifact chain.",
            "target": {
              "type": "objective-id",
              "target-id": "local-model-version-traceability",
              "status": {
                "state": "satisfied"
              }
            },
            "related-observations": [
              {
                "observation-uuid": "57612a85-4e1b-47fb-bd3c-8090fd17ec36"
              }
            ]
          }
        ]
      }
    ],
    "back-matter": {
      "resources": [
        {
          "uuid": "7bd39e11-3e12-49f8-805d-31189a91ee3f",
          "title": "Model lineage telemetry artifact",
          "description": "Automated model lineage telemetry extract",
          "rlinks": [
            {
              "href": "https://example.test/evidence/model-lineage-2026-11-19.json"
            }
          ]
        }
      ]
    }
  }
}
JSON
```


