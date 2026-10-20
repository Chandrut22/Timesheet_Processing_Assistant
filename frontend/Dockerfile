# syntax=docker/dockerfile:1
# Timesheet Assistant frontend: build with Node, serve with nginx (non-root, port 8080).

# ---- build ----------------------------------------------------------------
FROM node:22-alpine AS build
WORKDIR /app

COPY package.json package-lock.json* ./
RUN if [ ! -f package-lock.json ]; then \
      echo "ERROR: frontend/package-lock.json is missing. Run 'npm install' in frontend/ and commit package-lock.json, then build again." >&2; \
      exit 1; \
    fi
RUN npm ci --legacy-peer-deps

COPY . .

# Optional: Jaeger UI base URL for the "Open trace" links (Vite reads it at build time).
ARG VITE_JAEGER_URL=""
ENV VITE_JAEGER_URL=${VITE_JAEGER_URL}
RUN npm run build

# ---- run ------------------------------------------------------------------
FROM nginx:1.27.5-alpine

# Our own main config (listens on 8080, pid and temp files in /tmp).
RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=build /app/dist /usr/share/nginx/html

USER nginx
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8080/healthz || exit 1
