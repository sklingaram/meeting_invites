#!/bin/bash
# Deploy Event Sync Service on EC2 (Ubuntu/Amazon Linux 2023)
# Run as root or with sudo

set -e

APP_DIR="/opt/event-sync"
APP_USER="www-data"

echo "=== Installing system dependencies ==="
if command -v apt-get &> /dev/null; then
    apt-get update
    apt-get install -y python3 python3-venv nginx
elif command -v dnf &> /dev/null; then
    dnf install -y python3 python3-pip nginx
fi

echo "=== Setting up application directory ==="
mkdir -p "$APP_DIR"
cp -r app/ data/ templates/ requirements.txt gunicorn.conf.py "$APP_DIR/"

echo "=== Creating Python virtual environment ==="
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"
"$APP_DIR/venv/bin/pip" install gunicorn

echo "=== Setting permissions ==="
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo "=== Installing systemd service ==="
cp event-sync.service /etc/systemd/system/event-sync.service
systemctl daemon-reload
systemctl enable event-sync
systemctl start event-sync

echo "=== Configuring nginx ==="
cp nginx.conf /etc/nginx/sites-available/event-sync
ln -sf /etc/nginx/sites-available/event-sync /etc/nginx/sites-enabled/event-sync
rm -f /etc/nginx/sites-enabled/default

# Test nginx config
nginx -t

systemctl restart nginx

echo "=== Deployment complete ==="
echo "Service status:"
systemctl status event-sync --no-pager
echo ""
echo "App should be accessible at http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo 'your-ec2-ip')/"
