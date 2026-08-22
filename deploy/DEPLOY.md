# Nasazení na VPS (2 GB RAM, vlastní doména, HTTPS)

Postup pro čistý Ubuntu/Debian VPS, kde ještě není Docker a na portech 80/443
nic neběží. Výsledek:

```
Internet ──443/80──► Caddy (hostitel, TLS)
                        └──► 127.0.0.1:8080 ──► kontejner: Nginx + FastAPI
                                                     └──► MongoDB (interní síť)
Teltonika ──5027/TCP──────────────────────────► kontejner
```

Celý postup zabere zhruba 20 minut, z toho polovinu build frontendu.

---

## 1. Swap (na 2 GB stroji nutný)

Build Reactu potřebuje ~1,5 GB. Bez swapu ho kernel na 2GB stroji zabije
a Docker ohlásí jen `exit code 137`.

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h          # ověření: Swap 2,0Gi
```

## 2. Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
```

Odhlaste se a přihlaste znovu (aby se projevilo členství ve skupině), pak:

```bash
docker --version && docker compose version
```

## 3. Stažení aplikace

```bash
sudo mkdir -p /opt && sudo chown "$USER" /opt
cd /opt
git clone https://github.com/martinjebest66/Fleet-final.git
cd Fleet-final
```

## 4. Konfigurace

```bash
cp .env.example .env
openssl rand -hex 32        # vygenerovaný řetězec vložte jako JWT_SECRET
nano .env
```

Pro tuhle sestavu (2 GB VPS, Caddy na hostiteli):

```env
JWT_SECRET=<vložte vygenerovaný řetězec>
ADMIN_EMAIL=vas@email.cz
ADMIN_PASSWORD=<vlastní heslo, min. 10 znaků>

ENVIRONMENT=production

# TLS terminuje Caddy na hostiteli
COOKIE_SECURE=true
COOKIE_SAMESITE=lax
HTTP_BIND=127.0.0.1
HTTP_PORT=8080

# 2 GB RAM
NODE_MAX_OLD_SPACE_MB=1536
APP_MEM_LIMIT=768m
MONGO_MEM_LIMIT=512m
```

`.env` je v `.gitignore`, do repozitáře se nedostane.

> Aplikace se **záměrně nespustí**, pokud `JWT_SECRET` chybí nebo je to známá
> výchozí hodnota, nebo pokud `ADMIN_PASSWORD` chybí či je příliš krátké.
> Důvod vypíše do logu.

## 5. Spuštění

```bash
docker compose up -d --build
docker compose logs -f app
```

V logu má být:

```
Fleet Manager 1.1.0 se spouští: {...}
MongoDB connected (mongodb:27017/fleet_manager) after 1 attempt(s)
Indexy připraveny: 37 vytvořeno/ověřeno, 0 selhalo
Administrátorský účet vytvořen: vas@email.cz
Teltonika TCP server listening on 0.0.0.0:5027
Start dokončen — API je připraveno.
```

Ověření zevnitř serveru (zvenčí zatím nejde, běží jen na loopbacku):

```bash
curl -s http://127.0.0.1:8080/api/health
# {"status":"ok","database":"up","teltonika":true,...}
```

## 6. Caddy a HTTPS

Nejdřív nasměrujte **A záznam** své domény na IP serveru a počkejte, než se
projeví (`dig +short fleet.example.cz`). Bez toho Let's Encrypt certifikát
nevydá.

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy

sudo cp deploy/Caddyfile.example /etc/caddy/Caddyfile
sudo nano /etc/caddy/Caddyfile      # doplňte doménu a e-mail
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Certifikát si Caddy vyžádá sám při prvním požadavku a sám ho obnovuje.

## 7. Firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 5027/tcp     # Teltonika trackery
sudo ufw enable
sudo ufw status
```

Port **27017 (MongoDB) neotvírejte** — databáze běží bez hesla a je dostupná
jen v interní Docker síti.

## 8. Kontrola

```bash
curl -sI https://fleet.example.cz/api/health   # HTTP/2 200
```

Přihlaste se na `https://fleet.example.cz` údaji z `ADMIN_EMAIL` /
`ADMIN_PASSWORD`.

## 9. Trackery

V konfigurátoru Teltonika nastavte:

| Položka | Hodnota |
|---|---|
| Server | `fleet.example.cz` (nebo IP serveru) |
| Port | `5027` |
| Protokol | TCP |
| Codec | Codec 8 nebo Codec 8 Extended |

Pak v aplikaci **GPS sledování → Zařízení** zaregistrujte IMEI a přiřaďte
vozidlo. Data z neregistrovaného IMEI se zahazují (v logu `Neznámé IMEI …`).

Kontrola, co zařízení skutečně posílá — a pod kterým AVL ID chodí tachometr:

```
GET /api/gps/devices/{imei}/raw-io
```

## 10. Zálohování

Databáze je v Docker volume `mongo_data`. Nastavte denní zálohu:

```bash
sudo mkdir -p /var/backups/fleet
crontab -e
```

```cron
0 3 * * * cd /opt/Fleet-final && ./deploy/backup.sh >> /var/log/fleet-backup.log 2>&1
```

Obnova ze zálohy:

```bash
docker compose exec -T mongodb mongorestore --archive --gzip --drop \
  < /var/backups/fleet/fleet-2026-08-22_0300.archive.gz
```

Zálohy kopírujte i mimo server — VPS umí zmizet i s disky.

---

## Aktualizace

```bash
cd /opt/Fleet-final
./deploy/backup.sh            # nejdřív záloha
git pull
docker compose up -d --build
docker compose logs -f app
```

> **Nikdy nepoužívejte `docker compose down -v`** — smaže volume `mongo_data`,
> tedy celou databázi. Na restart stačí `docker compose restart`.

## Přenos dat ze starého nasazení

Data ze staré instance se **nepřenesou samy** — nový server startuje
s prázdným volume. Nejčastější past: stará instance běžela s jiným jménem
databáze (na platformě Emergent to bylo `test_database`), takže data v Mongu
sice jsou, ale aplikace se dívá do `fleet_manager` a hlásí prázdno.

Co je kde, ukáže diagnostika:

```bash
./deploy/diagnose.sh
```

Vypíše všechny databáze s počty záznamů a na kterou se aplikace dívá.

**Data jsou v Mongu pod jiným jménem** — stačí přepnout aplikaci:

```bash
nano .env          # DB_NAME=test_database
docker compose up -d
```

**Data jsou ještě na starém serveru** — vyexportovat a nahrát:

```bash
# na starém serveru
mongodump --uri="mongodb://127.0.0.1:27017" --db test_database --archive=stara.gz --gzip

# přenos a import (druhý parametr = jméno zdrojové databáze)
scp stara.gz novy-server:/opt/Fleet-final/
./deploy/import-legacy-data.sh stara.gz test_database
docker compose restart app
```

Import si předtím udělá zálohu současného stavu a jména databází přemapuje,
takže data skončí tam, kam se aplikace dívá.

## Když něco nefunguje

| Příznak | Kde hledat |
|---|---|
| Kontejner se nespustí | `docker compose logs app` — konfigurační chyby se vypisují jako CRITICAL |
| Build skončí `exit code 137` | Málo paměti: zkontrolujte swap (krok 1), snižte `NODE_MAX_OLD_SPACE_MB` na 1024 |
| Web hlásí 502 | Kontejner neběží nebo neposlouchá: `docker compose ps`, `curl 127.0.0.1:8080/api/health` |
| Přihlášení projde, ale data se nenačtou | `COOKIE_SECURE=true` **bez** HTTPS: prohlížeč cookie zahodí a každý další požadavek skončí 401. Přes HTTPS naopak funguje i bez něj (jen je to méně bezpečné). |
| Certifikát se nevydá | A záznam nemíří na server, nebo port 80 není otevřený |
| Tracker se nepřipojí | `./deploy/diagnose.sh` — ukáže port, firewall, registrovaná IMEI i neznámá IMEI z logu |
| Na živé mapě nic není | Vozidlo musí mít registrované IMEI (záložka Zařízení) a tracker musí poslat alespoň jednu pozici s platným fixem |
| Po nasazení chybí data | `./deploy/diagnose.sh` → sekce „Co je ve všech databázích" (viz Přenos dat výše) |
| Tachometr chybí | `GET /api/gps/devices/{imei}/raw-io`, viz `CAN_VEHICLE_MILEAGE_IO_IDS` v README |

Stav aplikace kdykoli:

```bash
docker compose ps
curl -s https://fleet.example.cz/api/health
docker stats --no-stream
```
