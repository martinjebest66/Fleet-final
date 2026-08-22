# ============================================
# Fleet Manager — multi-stage image
#   Stage 1: build the React frontend
#   Stage 2: Python backend + Nginx serving the build
# ============================================

# --- Stage 1: build frontend ---
FROM node:20-alpine AS frontend-build
WORKDIR /build

# Copy the manifest first so the dependency layer is cached across source edits.
COPY frontend/package.json frontend/yarn.lock ./
# --frozen-lockfile without a fallback: an install that silently resolves
# different versions than the committed lockfile makes builds unreproducible.
RUN yarn install --frozen-lockfile --network-timeout 600000

COPY frontend/ ./

# Empty = the frontend calls /api on the origin it was served from, which is
# what the bundled Nginx configuration provides.
ARG REACT_APP_BACKEND_URL=""
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL
# CI treats warnings as errors in create-react-app builds; keep them visible
# without failing the image build on a lint warning.
ENV CI=false
# Source maps roughly double the peak memory and disk of the build and are not
# shipped anyway.
ENV GENERATE_SOURCEMAP=false
# Webpack needs considerably more than Node's default heap for this bundle.
# Without an explicit ceiling the build dies on a small VPS with
# "JavaScript heap out of memory", or the kernel OOM-kills it and Docker
# reports a bare "exit code 137". Override at build time:
#   docker compose build --build-arg NODE_MAX_OLD_SPACE_MB=1536
ARG NODE_MAX_OLD_SPACE_MB=2048
ENV NODE_OPTIONS="--max-old-space-size=${NODE_MAX_OLD_SPACE_MB}"

RUN node -e "console.log('Node heap limit (MB):', Math.round(require('v8').getHeapStatistics().heap_size_limit / 1048576))" \
    && yarn build

# --- Stage 2: production image ---
FROM python:3.11-slim
LABEL org.opencontainers.image.title="Fleet Manager" \
      org.opencontainers.image.description="Správa vozového parku autoškoly"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        nginx curl tini \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/nginx/sites-enabled/default

WORKDIR /app/backend

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./

COPY --from=frontend-build /build/build /var/www/html

COPY deploy/nginx.conf /etc/nginx/sites-available/default
RUN ln -sf /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default

COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose:
#   80   - Nginx (frontend + API proxy)
#   5027 - Teltonika TCP receiver
EXPOSE 80 5027

# The health endpoint reports the database connection too, so an instance that
# is up but cannot reach MongoDB is reported unhealthy rather than ready.
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=5 \
    CMD curl -fsS http://127.0.0.1/api/health || exit 1

# tini reaps the Nginx/Uvicorn children and forwards signals, so `docker stop`
# results in a graceful shutdown instead of a SIGKILL after the timeout.
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/entrypoint.sh"]
