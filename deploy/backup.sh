#!/bin/bash
# Záloha databáze Fleet Manageru.
#
#   ./deploy/backup.sh [cílový_adresář]
#
# Vytvoří komprimovaný mongodump z běžícího kontejneru a smaže zálohy starší
# než BACKUP_KEEP_DAYS. Vhodné pustit z cronu:
#
#   0 3 * * * cd /opt/Fleet-final && ./deploy/backup.sh >> /var/log/fleet-backup.log 2>&1
#
# Obnova:
#   docker compose exec -T mongodb mongorestore --archive --gzip --drop < zaloha.gz
set -euo pipefail

BACKUP_DIR="${1:-/var/backups/fleet}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
DB_NAME="${DB_NAME:-fleet_manager}"
CONTAINER="${MONGO_CONTAINER:-fleet-mongo}"

timestamp="$(date +%Y-%m-%d_%H%M)"
target="${BACKUP_DIR}/fleet-${timestamp}.archive.gz"

mkdir -p "$BACKUP_DIR"

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    echo "[backup] Kontejner $CONTAINER neběží — záloha přeskočena." >&2
    exit 1
fi

echo "[backup] $(date '+%F %T') Zálohuji databázi $DB_NAME do $target"
# Nejdřív do dočasného souboru: přerušený dump nesmí vypadat jako hotová záloha.
docker exec "$CONTAINER" mongodump --db "$DB_NAME" --archive --gzip > "${target}.part"
mv "${target}.part" "$target"

size="$(du -h "$target" | cut -f1)"
echo "[backup] Hotovo, velikost $size"

deleted=$(find "$BACKUP_DIR" -name 'fleet-*.archive.gz' -mtime "+${KEEP_DAYS}" -print -delete | wc -l)
[ "$deleted" -gt 0 ] && echo "[backup] Smazáno $deleted starých záloh (starších než ${KEEP_DAYS} dní)"

echo "[backup] Zálohy v $BACKUP_DIR:"
ls -1sh "$BACKUP_DIR" | tail -5
