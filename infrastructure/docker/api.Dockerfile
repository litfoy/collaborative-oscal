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
COPY infrastructure/docker/init-credentials.py infrastructure/docker/api-entrypoint.sh /opt/compose/
ENV PATH="/opt/app/apps/api/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1
USER 10001:10001
