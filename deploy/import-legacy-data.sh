#!/bin/bash
# Přenos dat ze starého nasazení do tohoto.
#
#   ./deploy/import-legacy-data.sh <soubor.archive.gz|adresář_dumpu> [zdrojová_db]
#
# Příklad — data ze starého serveru:
#   mongodump --uri="mongodb://starý-server:27017" --db test_database \
#             --archive=stara.gz --gzip
#   scp stara.gz novy-server:/opt/Fleet-final/
#   ./deploy/import-legacy-data.sh stara.gz test_database
#
# Skript data NEMAŽE: obnovuje s --nsInclude do cílové databáze a existující
# záznamy nepřepisuje (--noIndexRestore ponechá indexy vytvořené aplikací).
# Před spuštěním si udělá vlastní zálohu současného stavu.
set -euo pipefail

SOURCE="${1:-}"
SOURCE_DB="${2:-}"
TARGET_DB="${DB_NAME:-$(grep -E '^DB_NAME=' .env 2>/dev/null | cut -d= -f2)}"
TARGET_DB="${TARGET_DB:-fleet_manager}"
MONGO="${MONGO_CONTAINER:-fleet-mongo}"

if [ -z "$SOURCE" ]; then
    echo "Použití: $0 <soubor.archive.gz> [zdrojová_db]"
    echo
    echo "Databáze, které jsou teď v Mongu:"
    docker exec "$MONGO" mongosh --quiet --eval \
      'db.adminCommand("listDatabases").databases.forEach(d => print("  " + d.name))' 2>/dev/null
    echo
    echo "Cílová databáze aplikace: $TARGET_DB"
    exit 1
fi

if [ ! -e "$SOURCE" ]; then
    echo "!! Soubor $SOURCE neexistuje." >&2
    exit 1
fi

echo "[import] Cílová databáze: $TARGET_DB"
echo "[import] Nejdřív záloha současného stavu…"
./deploy/backup.sh >/dev/null
echo "[import] Záloha hotová."

restore_args=(--gzip --archive)
if [ -n "$SOURCE_DB" ]; then
    # Přemapování jména databáze: stará data se často jmenují jinak
    # (např. test_database) než databáze, na kterou se aplikace dívá.
    restore_args+=(--nsFrom "${SOURCE_DB}.*" --nsTo "${TARGET_DB}.*")
    echo "[import] Mapuji ${SOURCE_DB}.* -> ${TARGET_DB}.*"
fi

echo "[import] Obnovuji z $SOURCE …"
docker exec -i "$MONGO" mongorestore "${restore_args[@]}" < "$SOURCE"

echo "[import] Obsah cílové databáze:"
docker exec "$MONGO" mongosh --quiet --eval "
var d = db.getSiblingDB('${TARGET_DB}');
['vehicles','instructors','logbook','fuel_entries','gps_trips','vehicle_positions',
 'gps_devices','damage_reports','qr_handovers','maintenance','users'].forEach(function (c) {
  var n = d.getCollection(c).countDocuments({});
  if (n > 0) print('  ' + c + ': ' + n);
});"

echo
echo "[import] Hotovo. Restart aplikace (doplní chybějící pole u historických jízd):"
echo "  docker compose restart app && docker compose logs -f app"
