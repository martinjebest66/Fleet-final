#!/bin/bash
# Fleet Manager container entrypoint.
#
# Runs Nginx (frontend + API proxy) and Uvicorn (API + Teltonika TCP receiver)
# in one container. Both are supervised here: if either dies the container
# exits, so the restart policy can do its job instead of leaving a half-running
# instance that answers HTTP but records no GPS data.
set -euo pipefail

log() { echo "[entrypoint] $*"; }

log "Fleet Manager starting"

: "${BACKEND_HOST:=0.0.0.0}"
: "${BACKEND_PORT:=8001}"
: "${UVICORN_WORKERS:=1}"

if [ "${UVICORN_WORKERS}" != "1" ]; then
    # The Teltonika TCP listener and the ICS sync loop are in-process
    # singletons; more than one worker would bind the port twice and sync
    # every calendar N times.
    log "WARNING: UVICORN_WORKERS=${UVICORN_WORKERS} is not supported (TCP receiver must be a singleton). Forcing 1."
    UVICORN_WORKERS=1
fi

nginx -t

nginx_pid=""
backend_pid=""

shutdown() {
    log "Shutdown signal received"
    [ -n "$backend_pid" ] && kill -TERM "$backend_pid" 2>/dev/null || true
    [ -n "$nginx_pid" ] && nginx -s quit 2>/dev/null || true
    [ -n "$backend_pid" ] && wait "$backend_pid" 2>/dev/null || true
    log "Stopped"
    exit 0
}
trap shutdown TERM INT

log "Starting Nginx"
nginx -g 'daemon off;' &
nginx_pid=$!

log "Starting FastAPI on ${BACKEND_HOST}:${BACKEND_PORT} (Teltonika TCP on ${TELTONIKA_TCP_PORT:-5027})"
cd /app/backend
uvicorn server:app \
    --host "${BACKEND_HOST}" \
    --port "${BACKEND_PORT}" \
    --workers 1 \
    --proxy-headers \
    --forwarded-allow-ips '*' \
    --timeout-graceful-shutdown 20 &
backend_pid=$!

# Exit as soon as either process stops, so the container is restarted as a
# whole rather than silently losing one half of the application.
while true; do
    if ! kill -0 "$backend_pid" 2>/dev/null; then
        log "ERROR: backend exited"
        wait "$backend_pid" || true
        nginx -s quit 2>/dev/null || true
        exit 1
    fi
    if ! kill -0 "$nginx_pid" 2>/dev/null; then
        log "ERROR: nginx exited"
        kill -TERM "$backend_pid" 2>/dev/null || true
        exit 1
    fi
    sleep 5
done
