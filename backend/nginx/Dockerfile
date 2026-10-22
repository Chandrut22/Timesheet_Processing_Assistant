# syntax=docker/dockerfile:1
# Public entry point: builds the React app, then serves it and proxies the APIs.
# Build context is the REPO ROOT (see docker-compose.yml: context: ..).

# ---- build the SPA -----------------------------------------------------------
FROM node:22-alpine AS build
WORKDIR /app

COPY frontend/package.json frontend/package-lock.json* ./
RUN if [ ! -f package-lock.json ]; then \
      echo "ERROR: frontend/package-lock.json is missing. Run 'npm install' in frontend/ and commit it." >&2; \
      exit 1; \
    fi
RUN npm ci

COPY frontend/ ./

# Vite bakes this in at build time (the "Open trace" links). Passed from docker-compose.yml.
ARG VITE_JAEGER_URL=""
ENV VITE_JAEGER_URL=${VITE_JAEGER_URL}
RUN npm run build

# ---- serve + proxy -------------------------------------------------------------
FROM nginx:1.27.5-alpine

RUN rm -f /etc/nginx/conf.d/default.conf
COPY backend/nginx/nginx.conf            /etc/nginx/nginx.conf
COPY backend/nginx/security-headers.conf /etc/nginx/security-headers.conf
COPY --from=build /app/dist /usr/share/nginx/html

USER nginx
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8080/healthz || exit 1