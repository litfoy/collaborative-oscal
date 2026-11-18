FROM node:22-bookworm-slim AS build
WORKDIR /opt/app
COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/package.json
RUN npm ci --omit=optional
COPY apps/web ./apps/web
RUN npm --workspace apps/web run build

FROM node:22-bookworm-slim
WORKDIR /opt/app
COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/package.json
COPY --from=build /opt/app/apps/web ./apps/web
RUN rm -rf ./apps/web/node_modules
RUN npm ci --omit=dev
COPY infrastructure/docker/web-entrypoint.sh /opt/compose/web-entrypoint.sh
WORKDIR /opt/app/apps/web
RUN chown -R 10001:10001 /opt/app/apps/web /opt/app/node_modules /opt/compose
ENV NODE_ENV=production
USER 10001:10001
CMD ["node", "/opt/app/apps/web/node_modules/next/dist/bin/next", "start", "--hostname", "0.0.0.0", "--port", "3000"]
