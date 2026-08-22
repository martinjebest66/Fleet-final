# Nasazení Fleet Manageru na Azure VM (Ubuntu)

## Přehled architektury

```
Internet
   │
   ├── :443/:80 → reverzní proxy na hostiteli (TLS)
   │                  └── 127.0.0.1:8080 → Nginx v kontejneru
   │                            ├── React frontend
   │                            └── /api → FastAPI (:8001)
   └── :5027 (TCP)  → Teltonika GPS tracker přímo na FastAPI
```

Vše běží v jednom Docker kontejneru + MongoDB v druhém. Stačí `docker compose up`.

Kontejner se publikuje jen na `127.0.0.1:8080`, takže z internetu není dosažitelný
přímo — TLS terminuje proxy na hostiteli. Pokud proxy mít nechcete, nastavte
v `.env` `HTTP_BIND=0.0.0.0` a `HTTP_PORT=80` (viz `deploy/setup-https.sh`).

MongoDB nemá publikovaný port; je dostupná jen v interní Docker síti.
V Azure Network Security Group tedy stačí otevřít **443/80** (proxy)
a **5027/TCP** (GPS trackery) — nikdy 27017.

---

## Krok 1: Vytvoření Azure VM

1. Přihlas se na https://portal.azure.com
2. Klikni **Vytvořit prostředek** → **Virtuální počítač**
3. Nastav:
   - **Předplatné**: tvoje předplatné
   - **Skupina prostředků**: vytvoř novou (např. `fleet-manager-rg`)
   - **Název VM**: `fleet-manager-vm`
   - **Oblast**: `West Europe` (nebo nejbližší)
   - **Image**: **Ubuntu Server 24.04 LTS**
   - **Velikost**: `Standard_B2s` (2 vCPU, 4 GB RAM) — stačí na začátek
   - **Ověřování**: SSH klíč (doporučeno) nebo heslo
4. Klikni **Další: Disky** → nech výchozí (30 GB SSD stačí)
5. Klikni **Další: Sítě** → nech výchozí, veřejná IP se vytvoří automaticky
6. Klikni **Zkontrolovat a vytvořit** → **Vytvořit**
7. Po vytvoření si zapiš **veřejnou IP adresu** (např. `20.123.45.67`)

---

## Krok 2: Otevření portů (Network Security Group)

V Azure Portal → tvůj VM → **Sítě** → **Pravidla příchozího portu** → **Přidat**:

| Pravidlo | Port | Protokol | Poznámka |
|----------|------|----------|----------|
| HTTP     | 80   | TCP      | Webová aplikace |
| SSH      | 22   | TCP      | Správa serveru (už je) |
| GPS      | 5027 | TCP      | Teltonika tracker |

> ⚠️ Port 5027 je klíčový! Bez něj GPS tracker neprojde.

---

## Krok 3: Připojení k VM přes SSH

```bash
ssh azureuser@20.123.45.67
# nebo s klíčem:
ssh -i ~/.ssh/tvuj_klic.pem azureuser@20.123.45.67
```

---

## Krok 4: Instalace Dockeru

Zkopíruj a vlož tyto příkazy:

```bash
# Aktualizace systému
sudo apt update && sudo apt upgrade -y

# Instalace Dockeru
curl -fsSL https://get.docker.com | sudo sh

# Přidej se do docker skupiny (ať nemusíš psát sudo)
sudo usermod -aG docker $USER

# Instalace Docker Compose pluginu
sudo apt install -y docker-compose-plugin

# Odhlásit a znovu přihlásit (aby se skupiny načetly)
exit
```

Znovu se přihlas přes SSH a ověř:
```bash
docker --version
docker compose version
```

---

## Krok 5: Nahrání kódu na server

### Varianta A: Přes Git (doporučeno)
```bash
# Na serveru:
git clone https://github.com/TVUJ_REPO/fleet-manager.git
cd fleet-manager
```

### Varianta B: Přes SCP (bez Gitu)
```bash
# Na tvém lokálním počítači:
scp -r /cesta/k/projektu azureuser@20.123.45.67:~/fleet-manager

# Na serveru:
cd ~/fleet-manager
```

---

## Krok 6: Nastavení proměnných prostředí

```bash
# Vytvoř .env soubor v kořenu projektu
cp deploy/.env.example .env

# Uprav hodnoty:
nano .env
```

Obsah `.env`:
```env
JWT_SECRET=vygeneruj-nahodny-retezec-64-znaku
ADMIN_EMAIL=admin@autoskola.cz
ADMIN_PASSWORD=TvojeSilneHeslo123!
```

> 💡 Pro vygenerování náhodného JWT_SECRET:
> ```bash
> openssl rand -hex 32
> ```

---

## Krok 7: Spuštění aplikace

```bash
# Build a start (první spuštění trvá 3-5 minut)
docker compose up -d --build

# Sleduj logy:
docker compose logs -f app
```

Po úspěšném startu uvidíš:
```
[1/2] Starting Nginx...
[2/2] Starting FastAPI + Teltonika TCP...
INFO: Startup complete: admin seeded, Teltonika TCP started
```

---

## Krok 8: Ověření

```bash
# Test webu (měl by vrátit HTML)
curl http://localhost

# Test API
curl http://localhost/api/health

# Test TCP portu pro GPS tracker
nc -zv localhost 5027
```

Z prohlížeče otevři: `http://20.123.45.67` (tvoje Azure IP)

---

## Krok 9: Konfigurace GPS trackeru Teltonika FMB003

V Teltonika Configuratoru nastav:
- **Server**: `20.123.45.67` (tvoje Azure IP)
- **Port**: `5027`
- **Protokol**: TCP

---

## Krok 10: HTTPS s Let's Encrypt (volitelné, ale doporučené)

Pokud máš doménu (např. `fleet.autoskola.cz`):

```bash
# Nastav DNS A záznam: fleet.autoskola.cz → 20.123.45.67

# Instalace Certbot
sudo apt install -y certbot

# Zastavení kontejneru (certbot potřebuje port 80)
docker compose down

# Získání certifikátu
sudo certbot certonly --standalone -d fleet.autoskola.cz

# Certifikáty budou v /etc/letsencrypt/live/fleet.autoskola.cz/
```

Pro HTTPS přidej do `docker-compose.yml` volume s certifikáty a uprav nginx.conf.

---

## Užitečné příkazy

```bash
# Restart aplikace
docker compose restart

# Aktualizace (po git pull)
docker compose up -d --build

# Zobrazení logů
docker compose logs -f app
docker compose logs -f mongodb

# Záloha databáze
docker compose exec mongodb mongodump --out /data/db/backup

# Stav kontejnerů
docker compose ps
```

---

## Náklady

| Služba | Cena (přibližně) |
|--------|-------------------|
| Azure VM B2s | ~30 €/měsíc |
| SSD 30 GB | ~2 €/měsíc |
| Veřejná IP | ~4 €/měsíc |
| **Celkem** | **~36 €/měsíc** |

> 💡 Tip: Pro úsporu můžeš použít **Reserved Instance** (1 rok) — sleva ~40%.
