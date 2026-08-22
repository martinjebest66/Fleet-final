#!/bin/bash
# ============================================
# Let's Encrypt HTTPS setup pro Fleet Manager
#
# POZOR: tento skript řeší variantu, kdy TLS terminuje Nginx UVNITŘ
# kontejneru. Výchozí nasazení to nepotřebuje — kontejner poslouchá jen na
# 127.0.0.1:8080 a TLS terminuje reverzní proxy na hostiteli (Caddy, Nginx,
# Traefik). Tam stačí v .env nastavit COOKIE_SECURE=true a tento skript
# nespouštět.
#
# Použijte ho jen tehdy, když žádnou proxy na hostiteli mít nechcete.
# ============================================
set -e

DOMAIN="${1:-}"
EMAIL="${2:-}"

if [ -z "$DOMAIN" ] || [ -z "$EMAIL" ]; then
  echo "Použití: ./setup-https.sh <domena> <email>"
  echo "Příklad: ./setup-https.sh fleet.autoskola.cz admin@autoskola.cz"
  exit 1
fi

echo "=== HTTPS Setup pro $DOMAIN ==="

# 1. Instalace Certbot
echo "[1/4] Instalace Certbot..."
sudo apt-get update
sudo apt-get install -y certbot

# 2. Zastavení kontejneru (certbot potřebuje port 80)
echo "[2/4] Zastavení kontejneru..."
docker compose down

# 3. Získání certifikátu
echo "[3/4] Získání certifikátu..."
sudo certbot certonly --standalone \
  -d "$DOMAIN" \
  --non-interactive \
  --agree-tos \
  -m "$EMAIL"

CERT_DIR="/etc/letsencrypt/live/$DOMAIN"

# 4. Vytvoření HTTPS nginx konfigurace
echo "[4/4] Generování HTTPS konfigurace..."
cat > deploy/nginx-https.conf << NGINX_EOF
server {
    listen 80;
    server_name $DOMAIN;
    return 301 https://\$host\$request_uri;
}

server {
    listen 443 ssl http2;
    server_name $DOMAIN;

    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;

    # HSTS
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    root /var/www/html;
    index index.html;

    client_max_body_size 32M;

    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/javascript application/javascript
               application/json application/xml image/svg+xml;

    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header Referrer-Policy "same-origin" always;
    server_tokens off;

    location = /healthz {
        proxy_pass http://127.0.0.1:8001/api/health;
        proxy_set_header Host \$host;
        access_log off;
    }

    # `location /api` without the trailing slash also matches a bare /api
    # request; with /api/ only, that request fell through to the SPA fallback.
    location /api {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_connect_timeout 10s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
        proxy_buffering off;
    }

    location /static/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
        try_files \$uri =404;
    }

    location = /index.html {
        add_header Cache-Control "no-cache, no-store, must-revalidate";
        expires off;
    }

    # SPA fallback
    location / {
        try_files \$uri \$uri/ /index.html;
    }
}
NGINX_EOF

echo ""
echo "=== HTTPS certifikát připraven! ==="
echo ""
echo "Další kroky:"
echo "1. Upravte docker-compose.yml - přidejte volume pro certifikáty:"
echo ""
echo "   volumes:"
echo "     - /etc/letsencrypt:/etc/letsencrypt:ro"
echo ""
echo "2. Vystavte kontejner přímo (výchozí je jen loopback) — v .env:"
echo "     HTTP_BIND=0.0.0.0"
echo "     HTTP_PORT=80"
echo "     COOKIE_SECURE=true      # bez toho prohlížeč zahodí session cookie"
echo ""
echo "   a v docker-compose.yml doplňte do ports mapování pro 443:"
echo "     - \"443:443\""
echo ""
echo "3. Přejmenujte nginx-https.conf:"
echo "   cp deploy/nginx-https.conf deploy/nginx.conf"
echo ""
echo "4. Rebuild a spusťte:"
echo "   docker compose up -d --build"
echo ""
echo "5. Nastavte automatickou obnovu certifikátu:"
echo "   sudo crontab -e"
echo "   # Přidejte řádek:"
echo "   0 3 * * * certbot renew --pre-hook 'docker compose -f $(pwd)/docker-compose.yml down' --post-hook 'docker compose -f $(pwd)/docker-compose.yml up -d'"
echo ""
echo "Hotovo!"
