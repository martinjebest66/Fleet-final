#!/bin/bash
# ============================================
# Let's Encrypt HTTPS setup pro Fleet Manager
# Spustit na Azure VM po prvním nasazení
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

    # API proxy
    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 120s;
        client_max_body_size 20M;
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
echo "2. Přidejte port 443:"
echo "   ports:"
echo "     - \"80:80\""
echo "     - \"443:443\""
echo "     - \"5027:5027\""
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
