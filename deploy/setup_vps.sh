#!/bin/bash
# BP Tracker — VPS setup script
# Run once on a fresh Ubuntu/Debian server as root or with sudo.
# Usage: bash setup_vps.sh

set -e
APP_DIR="/home/ubd/bp_tracker"
SERVICE_USER="ubd"

echo "========================================"
echo "  BP Tracker — VPS Setup"
echo "========================================"

# ── System dependencies ───────────────────────────────────────────────────
echo ""
echo "→ Installing system packages..."
apt-get update --allow-releaseinfo-change -qq
apt-get install -y -qq curl git nginx certbot python3-certbot-nginx

# ── uv ────────────────────────────────────────────────────────────────────
echo "→ Installing uv..."
if ! command -v uv &> /dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# ── Clone repo ────────────────────────────────────────────────────────────
echo "→ Cloning repository..."
if [ -d "$APP_DIR" ]; then
    echo "  Directory exists — pulling latest..."
    cd "$APP_DIR" && git pull
else
    git clone https://github.com/UtkuBilenDemir/bp_tracker.git "$APP_DIR"
fi
cd "$APP_DIR"

# ── Python environment ────────────────────────────────────────────────────
echo "→ Installing Python dependencies..."
uv sync

# ── .env ──────────────────────────────────────────────────────────────────
if [ ! -f "$APP_DIR/.env" ]; then
    echo ""
    read -rp "Anthropic API key: " API_KEY
    echo "ANTHROPIC_API_KEY=$API_KEY" > "$APP_DIR/.env"
    echo "→ .env created."
else
    echo "→ .env already exists, skipping."
fi

# ── data directory ────────────────────────────────────────────────────────
mkdir -p "$APP_DIR/data"
chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR/data"

# ── Initial htpasswd (user: bilen) ────────────────────────────────────────
echo ""
read -rp "Dashboard password for user 'bilen' [default: bilen]: " PASSWD
PASSWD="${PASSWD:-bilen}"

uv run python -c "
from passlib.apache import HtpasswdFile
ht = HtpasswdFile('data/.htpasswd', new=True)
ht.set_password('bilen', '$PASSWD')
ht.save()
print('  htpasswd created.')
"

# ── systemd service ───────────────────────────────────────────────────────
echo "→ Installing systemd service..."
cp "$APP_DIR/deploy/bp-tracker.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable bp-tracker
systemctl start bp-tracker
echo "  Service started."

# ── nginx ─────────────────────────────────────────────────────────────────
echo "→ Configuring nginx..."
cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/bp-tracker
ln -sf /etc/nginx/sites-available/bp-tracker /etc/nginx/sites-enabled/bp-tracker
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
echo "  nginx configured."

# ── SSL ───────────────────────────────────────────────────────────────────
echo ""
read -rp "Email for SSL certificate (Let's Encrypt): " SSL_EMAIL
certbot --nginx -d bp.utkubilen.de --non-interactive --agree-tos -m "$SSL_EMAIL"
echo "  SSL certificate issued."

# ── Done ──────────────────────────────────────────────────────────────────
echo ""
echo "========================================"
echo "  Setup complete!"
echo "  Dashboard: https://bp.utkubilen.de"
echo "  Login: bilen / $PASSWD"
echo "  Manage users from within the dashboard."
echo "========================================"
