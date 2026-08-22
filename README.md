# Fleet Manager

Správa vozového parku autoškoly: vozidla, kniha jízd, tankování, poškození,
předávací protokoly, údržba, GPS sledování (Teltonika FMB003), import jízd
z Ruhaviku, synchronizace rezervačního kalendáře (ICS) a reporty.

```
Browser ──► Nginx :80 ──┬──► React build (SPA)
                        └──► /api ──► FastAPI :8001 ──► MongoDB :27017
                                          │
Teltonika GPS tracker ──► TCP :5027 ───────┘
```

Frontend i API běží na **jednom originu**. Prohlížeč tedy posílá first-party
cookies a CORS se vůbec neuplatní — proto je `REACT_APP_BACKEND_URL` normálně
prázdný a frontend volá relativní `/api/...`.

---

## Rychlý start (Docker)

```bash
cp .env.example .env

# Vygenerujte vlastní secret a heslo administrátora:
python3 -c "import secrets; print(secrets.token_hex(32))"   # -> JWT_SECRET
# ADMIN_PASSWORD zvolte vlastní, minimálně 10 znaků

docker compose up -d --build
docker compose logs -f app
```

Aplikace poslouchá na **`127.0.0.1:8080`** — tedy jen na loopbacku. Před ni
patří reverzní proxy na hostiteli (Caddy, Nginx, Traefik), která terminuje TLS.
Ověření zevnitř serveru:

```bash
curl -s http://127.0.0.1:8080/api/health
```

Pokud reverzní proxy nemáte a chcete kontejner vystavit přímo, nastavte v `.env`:

```env
HTTP_BIND=0.0.0.0
HTTP_PORT=80
```

Port trackerů `5027/TCP` zůstává na veřejném rozhraní — Teltonika se připojuje
z mobilní sítě, loopback by GPS data tiše zastavil.

> **Pozor:** `docker compose down -v` smaže volume `mongo_data`, tedy celou
> databázi (vozidla, kniha jízd, GPS historie). Na produkčním serveru ho
> nepoužívejte. Pro restart stačí `docker compose restart` nebo
> `docker compose up -d --build`.

### Co se stane při špatné konfiguraci

Aplikace **záměrně nenastartuje**, pokud:

* `JWT_SECRET` chybí, je kratší než 32 znaků nebo jde o veřejně známou
  výchozí hodnotu,
* `ADMIN_PASSWORD` chybí, je kratší než 10 znaků nebo jde o známé výchozí heslo,
* `CORS_ORIGINS=*` je zkombinováno s cookie autentizací,
* `COOKIE_SAMESITE=none` bez `COOKIE_SECURE=true`.

Důvod je v logu (`docker compose logs app`). Tiché použití známého secretu je
horší než pád — kdokoli, kdo viděl tento repozitář, by mohl padělat tokeny.

---

## Konfigurace

Všechny proměnné jsou popsané v [`.env.example`](.env.example). Nejdůležitější:

| Proměnná | Výchozí | Význam |
|---|---|---|
| `JWT_SECRET` | — | **povinné**, podpis session tokenů |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | — | **povinné**, prvotní účet administrátora |
| `ENVIRONMENT` | `production` | `development` uvolní kontroly a zapne ukázková data |
| `MONGO_URL` / `DB_NAME` | `mongodb://mongodb:27017` / `fleet_manager` | databáze |
| `COOKIE_SECURE` | `false` | nastavte `true`, pokud před aplikací terminujete TLS |
| `COOKIE_SAMESITE` | `lax` | `none` jen při frontendu na jiné doméně (vyžaduje `COOKIE_SECURE=true`) |
| `CORS_ORIGINS` | prázdné | seznam originů; prázdné = same-origin, middleware se vůbec nepřidá |
| `REACT_APP_BACKEND_URL` | prázdné | build-time; prázdné = relativní `/api` |
| `HTTP_BIND` / `HTTP_PORT` | `127.0.0.1` / `8080` | kde se publikuje web; `0.0.0.0` vystaví kontejner přímo |
| `TELTONIKA_BIND` / `TELTONIKA_TCP_PORT` | `0.0.0.0` / `5027` | port TCP přijímače GPS trackerů |
| `NODE_MAX_OLD_SPACE_MB` | `2048` | velikost Node heapu při buildu frontendu |
| `APP_MEM_LIMIT` / `MONGO_MEM_LIMIT` | `1g` / `1g` | paměťové stropy běžících kontejnerů |
| `ALLOW_MOCK_DATA` | `false` (v produkci) | generátory ukázkových GPS dat |
| `ADMIN_PASSWORD_RESET_ON_START` | `false` | přepsat heslo admina při každém startu |
| `ICS_ALLOW_PRIVATE_HOSTS` | `false` | povolit ICS kalendáře na interních adresách |

### HTTPS

Nasazení za reverzní proxy s TLS (Caddy, Traefik, Nginx):

```env
COOKIE_SECURE=true
COOKIE_SAMESITE=lax
```

Aplikace čte `X-Forwarded-Proto`; proxy ho musí posílat.

### Paměť

Build Reactu je nejnáročnější část nasazení. Webpack potřebuje výrazně víc než
výchozí Node heap; na malém VPS build jinak skončí hláškou
`JavaScript heap out of memory`, nebo ho zabije kernel a Docker ohlásí jen
`exit code 137`. Velikost heapu je proto explicitní:

```env
NODE_MAX_OLD_SPACE_MB=1536   # 2 GB server
NODE_MAX_OLD_SPACE_MB=2048   # výchozí, 4 GB server
```

Jednorázově i bez `.env`:

```bash
docker compose build --build-arg NODE_MAX_OLD_SPACE_MB=1536
```

Běžící kontejnery mají strop `APP_MEM_LIMIT` a `MONGO_MEM_LIMIT` (výchozí 1 GB
každý). MongoDB si podle cgroup limitu sama zmenší WiredTiger cache, takže
nezabere všechnu RAM. Na serveru s 1 GB RAM buildujte obraz jinde
(`docker build` na silnějším stroji + `docker push`), místní build se tam
nevejde.

### MongoDB

Port `27017` **není** publikován na hostitele. Databáze běží bez autentizace
a je dostupná jen v interní Docker síti. Pokud potřebujete přístup zvenčí,
zapněte v MongoDB autentizaci a publikujte port cíleně (např. jen na
`127.0.0.1`), nikoli na `0.0.0.0`.

---

## Teltonika GPS trackery

Na trackeru nastavte server na veřejnou adresu tohoto hostitele, port `5027`,
protokol TCP, Codec 8 nebo Codec 8 Extended.

Poté v aplikaci (*GPS sledování → Zařízení*) zaregistrujte IMEI a přiřaďte ho
k vozidlu. **Data z neregistrovaného IMEI se zahazují** — v logu se objeví
`Neznámé IMEI …`.

Přijímač:

* rámuje pakety podle deklarované délky, takže zvládá jak rozdělený paket
  napříč několika TCP čteními, tak více paketů v jednom čtení,
* ověřuje CRC-16 a shodu počtu záznamů; vadný paket potvrdí nulou, takže ho
  tracker pošle znovu,
* nepotvrzuje záznamy, které se nepodařilo uložit — data se neztratí ani při
  výpadku databáze,
* stav najdete na `GET /api/gps/tcp-status`.

Data se ukládají nezávisle na tom, zda má někdo otevřený frontend.

---

## Jízdy, zdroje dat a reporty

Každá jízda má **zdroj**:

| Zdroj | Odkud pochází |
|---|---|
| `teltonika` | záznam z GPS trackeru (přímý příjem nebo automatická detekce jízd) |
| `ruhavik` | import z exportu Ruhaviku (CSV / GPX) |
| `manual` | ručně zapsaná jízda v knize jízd |
| `mock` | ukázková data — do reportů se **nezapočítávají** |

Reporty čtou jízdy přes jednu společnou vrstvu (`backend/trips.py`), takže
Ruhavik jízdy se počítají úplně stejně jako jízdy z trackeru — v přehledu
jízd, v celkových kilometrech, ve statistikách vozidla i učitele, v knize
jízd, v CSV i PDF exportu a na dashboardu. Filtrovat podle zdroje jde
(`?source=ruhavik`), ale výchozí report zahrnuje všechny reálné zdroje.

**Dvojí započítání** je ošetřeno na dvou místech:

* záznam v knize jízd vytvořený synchronizací GPS jízdy (`gps_source: true`)
  je jen projekcí té jízdy — počítá se jízda, ne projekce;
* jízda importovaná z Ruhaviku, kterou už zaznamenal tracker, se uloží
  s `duplicate_of` a do součtů nevstupuje. Záznam zůstane zachovaný,
  s `?include_duplicates=true` ho report zobrazí.

Detekce duplicity je záměrně opatrná: musí sedět vozidlo, **oba** konce jízdy
do 10 minut a vzdálenost v toleranci. Dvě různé jízdy, které se jen podobají
délkou nebo jsou ve stejný den, se nespojí.

### Import z Ruhaviku je idempotentní

Každá importovaná jízda dostane stabilní `external_id` — buď z exportu, nebo
odvozené z vozidla, časů a vzdálenosti. Opakovaný import stejného souboru tedy
nevytvoří duplicity; API vrátí počty:

```json
{
  "imported": 12,
  "skipped_already_imported": 40,
  "duplicates_of_tracker": 3,
  "rejected": 1,
  "errors": ["řádek 7: nečitelný čas začátku jízdy"]
}
```

Jeden vadný řádek nikdy neshodí zbytek souboru.

---

## Stav tachometru a paliva k datu

Otázku „jaký stav tachometru a paliva mělo vozidlo k určitému datu?" zodpovídá
tlačítko **Stav tachometru a paliva** na kartě vozidla. Po zvolení data se
zobrazí odečet, graf vývoje za období a tabulka po dnech; u GPS jízdy se stav
na začátku a na konci ukáže přímo v detailu trasy.

Údaje se nikde neukládají podruhé — skládají se ze záznamů, které aplikace
vede tak jako tak:

| Zdroj | Co dává |
|---|---|
| Tachometr vozidla (CAN) | **skutečný stav tachometru** z palubní jednotky — `can.vehicle.mileage` |
| GPS tracker | vzdálenost napočítaná zařízením a stav paliva |
| Tankování | odečet tachometru z palubní desky |
| Předávací protokol | odečet tachometru a stav palivoměru |
| Kniha jízd | tachometr na konci jízdy |

**Pokud lokátor posílá `can.vehicle.mileage`** (skutečný tachometr přečtený
přes CAN / OEM PID), použije se přímo — je to tentýž údaj, jaký je vidět na
palubní desce, takže se nic nedopočítává a neoznačuje jako odhad.

Když vozidlo tachometr nehlásí, spočítá se jako **poslední ručně zapsaný
odečet** plus vzdálenost, kterou od té doby napočítal tracker. Takový údaj je
vždy označen jako **odhad** a je u něj vidět, ze kterého záznamu vychází.
Když k datu žádný záznam neexistuje, vrátí se prázdná hodnota, ne nula.

Tracker po výměně začíná počítat od nuly; záporný přírůstek se nikdy
neodečítá.

### Které AVL ID nese tachometr

Teltonika posílá číslované IO prvky, ne názvy — které číslo nese tachometr,
závisí na modelu a na tom, jestli je připojený CAN adaptér. Výchozí mapování:

| Parametr | AVL ID | Jednotka |
|---|---|---|
| `can.vehicle.mileage` | 389 (OBD OEM Total Mileage) | km |
| `can.vehicle.mileage` | 87, 105 (CAN adaptér) | m |
| `can.tracker.counted.mileage` | 16 (Total Odometer) | m |
| `can.fuel.level` | 48, 89 | % |
| `can.fuel.level.liters` | 390 (OBD OEM Fuel Level) | 0,1 l |

Co konkrétní zařízení posílá, ukáže:

```
GET /api/gps/devices/{imei}/raw-io
```

Odpověď rozdělí prvky na `mapped` a `unmapped`. Když je tachometr mezi
`unmapped`, přidejte jeho ID do `CAN_VEHICLE_MILEAGE_IO_IDS` — formát `id`
u již známého ID, jinak `id:jednotka` (`m`, `km`, `l`, `dl`, `%`).
Samotné neznámé ID se odmítne místo hádání jednotky: záměna metrů za
kilometry by tachometr nafoukla tisíckrát.

> FMB003 potřebuje pro OEM parametry firmware 03.27.07.Rev.562 nebo novější;
> bez něj AVL 389/390 neposílá vůbec.

API:

| Endpoint | Popis |
|---|---|
| `GET /api/vehicles/{id}/state?at=2026-08-20` | stav k okamžiku vč. původu údaje |
| `GET /api/vehicles/{id}/state/history?date_from&date_to` | záznamy a denní přehled |
| `GET /api/gps/trips/{id}/route` | trasa + stav na začátku a na konci jízdy |

Hustý proud z trackeru se pro zobrazení prořezává (`max_points`); uložená data
zůstávají kompletní.

## Doklady k servisu a údržbě

Ke každé položce údržby lze připojit vyfocené doklady — fakturu, protokol
o STK, stránku ze servisní knihy, účtenku. Na telefonu otevře tlačítko
**Vyfotit doklad** rovnou fotoaparát, takže doklad se dá pořídit na místě
u servisu.

Přijímají se obrázky (JPEG, PNG, WebP, HEIC/HEIF) a PDF do
`MAX_UPLOAD_BYTES` (výchozí 10 MB). Ostatní typy se odmítnou.

Binární data leží v samostatné kolekci `maintenance_documents`, v položce
údržby zůstávají jen metadata. Seznam údržby proto zůstává malý i s desítkami
fotek a nehrozí naražení na 16MB limit dokumentu v MongoDB. Smazání položky
údržby smaže i její doklady.

| Endpoint | Popis |
|---|---|
| `POST /api/maintenance/{id}/documents` | nahrání dokladu (`file`, `doc_type`, `label`) |
| `GET /api/maintenance/documents/{doc_id}/file` | zobrazení / stažení dokladu |
| `DELETE /api/maintenance/documents/{doc_id}` | smazání dokladu (admin) |

## Reportovací API

| Endpoint | Popis |
|---|---|
| `GET /api/reports/trips` | jízdy ze všech zdrojů + souhrn |
| `GET /api/reports/trips/export-csv` | CSV export téhož |
| `GET /api/reports/km-stats` | kilometry po dnech a vozidlech |
| `GET /api/reports/vehicle/{id}` | statistiky jednoho vozidla |
| `GET /api/reports/instructor/{id}` | statistiky jednoho učitele |
| `GET /api/reports/dashboard` | dashboard |
| `GET /api/logbook/export-pdf` | kniha jízd v PDF (všechny zdroje) |

Společné parametry: `date_from`, `date_to`, `vehicle_id`, `instructor_id`,
`source`, `include_duplicates`.

---

## Vývoj

### Backend

```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt

export ENVIRONMENT=development
export JWT_SECRET=dev-secret
export MONGO_URL=mongodb://localhost:27017
export DB_NAME=fleet_manager_dev
export ADMIN_EMAIL=admin@example.com ADMIN_PASSWORD=dev-heslo-12345

uvicorn server:app --reload --port 8001
```

### Frontend

```bash
cd frontend
yarn install
yarn start          # dev server na :3000, proxy na backend
yarn lint
yarn build
```

### Testy

```bash
pytest                       # jednotkové + API testy (bez serveru a bez DB)
```

Testy běží proti in-memory MongoDB, takže nepotřebují databázi ani nasazenou
aplikaci. Pokrývají mimo jiné Teltonika parser a TCP rámování, import
z Ruhaviku a jeho idempotenci, deduplikaci jízd, reporty přes všechny zdroje,
autentizaci a autorizaci a kontrolu produkční konfigurace.

Integrační testy proti běžící instanci:

```bash
FLEET_BASE_URL=http://localhost \
FLEET_ADMIN_EMAIL=... FLEET_ADMIN_PASSWORD=... \
pytest tests/integration
```

---

## Struktura

```
backend/
  server.py       API endpointy, autentizace, reporty, ICS, rezervace
  config.py       konfigurace z prostředí + kontroly produkčního nasazení
  database.py     připojení k MongoDB, čekání na start, indexy
  trips.py        jednotný model jízdy a reportovací vrstva
  vehicle_state.py stav tachometru a paliva k datu (odvozený z ostatních záznamů)
  ruhavik.py      parsování Ruhavik exportů + idempotentní import
  teltonika.py    Codec 8 / 8E parser a TCP přijímač
  tests/          jednotkové a API testy
frontend/src/
  lib/api.js      základní URL API, sdílený axios klient, ošetření 401
  pages/          obrazovky aplikace
deploy/
  nginx.conf      reverzní proxy a servírování SPA
  entrypoint.sh   spuštění Nginx + Uvicorn v jednom kontejneru
tests/integration/  testy proti běžící instanci
```

## Diagnostika

```bash
docker compose logs -f app        # start, MongoDB, Teltonika, importy
curl -s http://localhost/api/health
```

V logu najdete start aplikace a shrnutí konfigurace (bez secretů), připojení
k MongoDB, stav TCP přijímače, připojení a odpojení trackerů včetně IMEI
a počtu přijatých AVL záznamů, chyby parsování paketů, výsledky Ruhavik
importů a chyby ICS synchronizace. Hesla, tokeny ani cookies se do logu
nezapisují.
