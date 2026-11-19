# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

FROM ghcr.io/astral-sh/uv:0.13.7 AS uv
FROM python:3.13-slim

COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /opt/app
COPY apps/api/pyproject.toml apps/api/uv.lock ./apps/api/
COPY packages/oscal ./packages/oscal
WORKDIR /opt/app/apps/api
RUN uv sync --locked --no-dev
COPY apps/api/app ./app
COPY alembic.ini /opt/app/alembic.ini
COPY migrations /opt/app/migrations
COPY apps/api/tests/fixtures/NIST_SP-800-53_rev5_catalog-min.json /opt/demo/nist-sp-800-53-rev5.json
COPY examples/catalogs/nist-ai-rmf-gen-ai-1.0.0-catalog.json /opt/demo/nist-ai-rmf-gen-ai-1.0.0-catalog.json
COPY examples/catalogs/nist-ai-rmf-gen-ai-1.0.0-catalog.provenance.json /opt/demo/nist-ai-rmf-gen-ai-1.0.0-catalog.provenance.json
COPY examples/catalogs/eu_ai_act_catalog.json /opt/demo/eu_ai_act_catalog.json
COPY examples/mappings/eu-ai-act_to_nist-genai_mapping-draft.json /opt/demo/eu-ai-act_to_nist-genai_mapping-draft.json
COPY infrastructure/docker/init-credentials.py infrastructure/docker/api-entrypoint.sh infrastructure/docker/seed-demo-catalog.py /opt/compose/
ENV PATH="/opt/app/apps/api/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1
USER 10001:10001
