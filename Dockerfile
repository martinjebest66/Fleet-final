# ============================================
# Multi-stage Dockerfile pro Fleet Manager
# Stage 1: Build React frontend
# Stage 2: Python backend + Nginx frontend
# ============================================

# --- Stage 1: Build frontend ---
FROM node:20-alpine AS frontend-build
WORKDIR /build

COPY frontend/package.json frontend/yarn.lock* ./
RUN yarn install --frozen-lockfile || yarn install

COPY frontend/ ./

# REACT_APP_BACKEND_URL se nastavi pri buildu - prazdne = relative URL
ARG REACT_APP_BACKEND_URL=""
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL

RUN yarn build

# --- Stage 2: Production image ---
FROM python:3.11-slim
LABEL maintainer="Fleet Manager <admin@autoskola.cz>"

# System deps + Nginx
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx curl && \
    rm -rf /var/lib/apt/lists/*

# Python deps
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Backend source
COPY backend/ ./

# Frontend build -> Nginx
COPY --from=frontend-build /build/build /var/www/html

# Nginx config
COPY deploy/nginx.conf /etc/nginx/sites-available/default

# Entrypoint script
COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose ports:
#   80   - Nginx (frontend + API proxy)
#   5027 - Teltonika TCP receiver
EXPOSE 80 5027

CMD ["/entrypoint.sh"]
