# AirWatch web image: the built frontend served by Caddy, which also terminates
# HTTPS and forwards /v1 to the API. Build from the repository root:
#   docker build -f infra/web/Dockerfile -t airwatch-web .

FROM node:22-alpine AS build
WORKDIR /src
COPY package.json package-lock.json ./
COPY frontend/package.json ./frontend/
RUN npm ci --workspace frontend --include-workspace-root=false --no-audit --no-fund
COPY frontend ./frontend
RUN npm --workspace frontend run build

FROM caddy:2-alpine
COPY infra/web/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /src/frontend/dist /srv/www
