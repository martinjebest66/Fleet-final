#!/bin/bash
# Diagnostika Fleet Manageru — pouze čte, nic nemění.
#
#   cd /opt/Fleet-final && ./deploy/diagnose.sh
#
# Odpovídá na dvě nejčastější otázky po nasazení:
#   „kde jsou moje data?"  a  „proč nechodí GPS?"
set -uo pipefail

APP="${APP_CONTAINER:-fleet-app}"
MONGO="${MONGO_CONTAINER:-fleet-mongo}"
BASE="${FLEET_BASE_URL:-http://127.0.0.1:${HTTP_PORT:-8080}}"

REPORT_FILE="${REPORT_FILE:-/tmp/fleet-report.txt}"
# Všechno jde i do souboru, aby se dal poslat jedním vložením.
exec > >(tee "$REPORT_FILE") 2>&1

hr() { printf '\n== %s ==\n' "$1"; }
mongo_eval() { docker exec "$MONGO" mongosh --quiet --eval "$1" 2>/dev/null; }

hr "Kontejnery"
docker compose ps 2>/dev/null || docker ps --filter "name=fleet-" \
  --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

if ! docker ps --format '{{.Names}}' | grep -qx "$APP"; then
    echo "!! Kontejner $APP neběží. Další kroky nemají smysl."
    echo "   docker compose logs app | tail -50"
    exit 1
fi

hr "Health"
curl -s --max-time 10 "$BASE/api/health" || echo "!! API neodpovídá na $BASE"
echo

hr "Konfigurace, na kterou se aplikace dívá"
# Hodnoty citlivých proměnných se maskují, aby šel výstup bezpečně sdílet.
docker exec "$APP" printenv 2>/dev/null \
  | grep -E '^(DB_NAME|MONGO_URL|ENVIRONMENT|COOKIE_SECURE|COOKIE_SAMESITE|CORS_ORIGINS|HTTP_BIND|HTTP_PORT|TELTONIKA_|ALLOW_MOCK_DATA|CAN_|ADMIN_EMAIL|JWT_SECRET|ADMIN_PASSWORD|RESEND_API_KEY|NODE_MAX|.*_MEM_)' \
  | sed -E 's/^(JWT_SECRET|ADMIN_PASSWORD|RESEND_API_KEY)=.*/\1=<skryto>/' \
  | sed -E 's#^(MONGO_URL=[a-z+]+://)[^@]*@#\1<skryto>@#' \
  | sort | sed 's/^/  /'
CONFIGURED_DB="$(docker exec "$APP" printenv DB_NAME 2>/dev/null || echo fleet_manager)"

hr "Reverzní proxy na hostiteli"
if [ -f /etc/caddy/Caddyfile ]; then
    echo "  /etc/caddy/Caddyfile:"
    grep -vE '^\s*#' /etc/caddy/Caddyfile | grep -vE '^\s*$' | sed 's/^/    /'
    systemctl is-active caddy >/dev/null 2>&1 \
      && echo "  caddy: běží" || echo "  caddy: NEBĚŽÍ (systemctl status caddy)"
else
    echo "  /etc/caddy/Caddyfile neexistuje"
    for svc in nginx apache2 traefik; do
        systemctl is-active "$svc" >/dev/null 2>&1 && echo "  pozor: běží $svc"
    done
fi
echo "  naslouchající porty na hostiteli:"
(ss -ltnp 2>/dev/null || netstat -ltnp 2>/dev/null) \
  | grep -E ':(80|443|8080|5027|27017)\b' | sed 's/^/    /' || echo "    (nezjištěno)"

hr "Zdroje serveru"
free -h 2>/dev/null | sed 's/^/  /'
df -h / 2>/dev/null | sed 's/^/  /'
docker stats --no-stream --format '  {{.Name}}: RAM {{.MemUsage}} CPU {{.CPUPerc}}' 2>/dev/null

hr "Co je ve všech databázích MongoDB"
# Nejdůležitější test: pokud data existují pod JINÝM jménem databáze,
# aplikace je nevidí, i když v Mongu leží.
mongo_eval '
db.adminCommand("listDatabases").databases.forEach(function (d) {
  if (["admin","local","config"].indexOf(d.name) >= 0) return;
  var conn = db.getSiblingDB(d.name);
  var parts = [];
  ["vehicles","instructors","logbook","fuel_entries","gps_trips",
   "vehicle_positions","gps_devices","damage_reports","qr_handovers",
   "maintenance","reservation_drives","users"].forEach(function (c) {
    var n = conn.getCollection(c).countDocuments({});
    if (n > 0) parts.push(c + "=" + n);
  });
  print("  " + d.name + "  (" + (d.sizeOnDisk/1048576).toFixed(1) + " MB)");
  print("      " + (parts.length ? parts.join(", ") : "prázdná / bez známých kolekcí"));
});'
echo "  --> aplikace používá databázi: ${CONFIGURED_DB}"
echo "      Leží-li data pod jiným jménem, nastavte DB_NAME v .env a"
echo "      spusťte: docker compose up -d"

hr "GPS: registrovaná zařízení"
mongo_eval "
var d = db.getSiblingDB('${CONFIGURED_DB}');
var devs = d.gps_devices.find({}, {_id:0, imei:1, vehicle_id:1, status:1, last_seen:1}).toArray();
if (!devs.length) {
  print('  ŽÁDNÉ zařízení není registrované.');
  print('  Data z neregistrovaného IMEI se zahazují — přidejte je v GPS sledování -> Zařízení.');
} else {
  devs.forEach(function (x) {
    print('  IMEI ' + x.imei + '  vozidlo=' + x.vehicle_id +
          '  stav=' + (x.status||'?') + '  naposledy=' + (x.last_seen||'nikdy'));
  });
}"

hr "GPS: uložené pozice a jízdy"
mongo_eval "
var d = db.getSiblingDB('${CONFIGURED_DB}');
print('  pozic celkem: ' + d.vehicle_positions.countDocuments({}));
var last = d.vehicle_positions.find({}, {_id:0, timestamp:1, imei:1, source:1})
             .sort({timestamp:-1}).limit(1).toArray()[0];
print('  poslední pozice: ' + (last ? last.timestamp + '  (' + (last.source||'?') + ', IMEI ' + (last.imei||'-') + ')' : 'žádná'));
print('  jízdy podle zdroje:');
d.gps_trips.aggregate([{\$group:{_id:'\$source', n:{\$sum:1}}}]).forEach(function (r) {
  print('    ' + (r._id || '(bez zdroje)') + ': ' + r.n);
});"

hr "Teltonika TCP přijímač"
docker exec "$APP" sh -c 'command -v ss >/dev/null && ss -ltn | grep 5027 || echo "  (ss není v obrazu)"' 2>/dev/null
echo "  z hostitele:"
timeout 5 bash -c 'cat < /dev/null > /dev/tcp/127.0.0.1/5027' 2>/dev/null \
  && echo "    port 5027 přijímá spojení" \
  || echo "    !! port 5027 NEODPOVÍDÁ na 127.0.0.1"
echo "  firewall:"
sudo ufw status 2>/dev/null | grep -E '5027|Status' | sed 's/^/    /' || echo "    (ufw nedostupné)"
# Trackery jsou prakticky vždy jen IPv4, takže se ptáme cíleně na IPv4 —
# `curl ifconfig.me` bez -4 klidně vrátí IPv6 adresu, na kterou se tracker
# nepřipojí.
ipv4="$(curl -4 -s --max-time 5 ifconfig.me 2>/dev/null)"
ipv6="$(curl -6 -s --max-time 5 ifconfig.me 2>/dev/null)"
echo "  veřejná IPv4: ${ipv4:-žádná}"
[ -n "$ipv6" ] && echo "  veřejná IPv6: $ipv6 (trackery ji zpravidla nepodporují)"
if [ -n "$ipv4" ]; then
    echo "    -> do trackeru patří tato IPv4 (nebo doména, která na ni míří) a port 5027/TCP"
else
    echo "    !! Server nemá veřejnou IPv4. Teltonika se na IPv6 zpravidla nepřipojí."
fi

hr "Log: neznámá IMEI a chyby"
docker compose logs --tail 2000 app 2>/dev/null | grep -E "Neznámé IMEI|Tracker connected|Invalid packet|CRITICAL|ERROR" \
  | tail -15 | sed 's/^/  /' || echo "  (nic)"

hr "Hotovo"
echo "Zálohu před jakoukoli opravou: ./deploy/backup.sh"
echo
echo "Celý výstup uložen do: ${REPORT_FILE:-(neukládá se)}"
echo "Hesla a secrets jsou v něm zamaskované, dá se bezpečně sdílet."
