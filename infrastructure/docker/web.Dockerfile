FROM node:22-bookworm-slim
WORKDIR /opt/app
COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/package.json
RUN npm ci --omit=optional
COPY apps/web ./apps/web
RUN npm --workspace apps/web run build
COPY infrastructure/docker/web-entrypoint.sh /opt/compose/web-entrypoint.sh
WORKDIR /opt/app/apps/web
ENV NODE_ENV=production
USER 10001:10001
CMD ["node", "/opt/app/node_modules/next/dist/bin/next", "start", "--hostname", "0.0.0.0", "--port", "3000"]
