# vestigo admin-ui — Vite + React SPA served by nginx.
#
# The browser hits the Admin API at `http://localhost:8001` (the host
# port mapped by Compose), so this image only needs to serve the built
# JS/HTML bundle on port 3000. No reverse-proxy logic — the SPA's typed
# fetch wrapper is configured at build time via `VITE_ADMIN_API_URL`,
# which defaults to `http://localhost:8001`.
#
# Two stages:
#   1. `builder` — node:20-alpine installs deps and produces `dist/`.
#   2. `runtime` — nginx:alpine serves `dist/` from /usr/share/nginx/html.

# --- Stage 1: builder ------------------------------------------------------

FROM node:20-alpine AS builder

WORKDIR /build

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .

# `vite build` writes to `dist/`. `tsc -b` runs first via the npm
# script, so a type error fails the image build — that's the point.
RUN npm run build


# --- Stage 2: runtime ------------------------------------------------------

FROM nginx:alpine AS runtime

# Replace the default nginx server with one that listens on 3000 and
# falls back to index.html for client-side routing.
COPY nginx.conf /etc/nginx/conf.d/default.conf

COPY --from=builder /build/dist /usr/share/nginx/html

EXPOSE 3000
