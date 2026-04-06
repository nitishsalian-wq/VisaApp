#!/bin/bash
# ============================================
# VisaDesk - DigitalOcean Droplet Setup Script
# Run this ONCE on a fresh Ubuntu droplet
# ============================================

set -e

echo "========================================"
echo "  VisaDesk - Droplet Setup"
echo "========================================"

# Update system
echo "[1/8] Updating system..."
apt update && apt upgrade -y

# Install Python, pip, nginx, supervisor
echo "[2/8] Installing Python, Nginx, Supervisor..."
apt install -y python3 python3-pip python3-venv nginx supervisor git ufw

# Create app user
echo "[3/8] Creating app user..."
useradd -m -s /bin/bash visadesk || true

# Create app directory
echo "[4/8] Setting up application directory..."
APP_DIR="/home/visadesk/app"
mkdir -p $APP_DIR
cd $APP_DIR

# Clone the repo (will be set by user)
echo "[5/8] Cloning repository..."
if [ -z "$GITHUB_REPO" ]; then
    echo "ERROR: Set GITHUB_REPO first. Example:"
    echo "  export GITHUB_REPO=https://github.com/yourusername/visadesk.git"
    exit 1
fi
git clone $GITHUB_REPO .

# Set up virtual environment and install dependencies
echo "[6/8] Installing Python dependencies..."
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Set up environment variables
echo "[7/8] Configuring environment..."
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
ADMIN_PASS=${ADMIN_PASSWORD:-admin123}

cat > /home/visadesk/.env <<ENVEOF
SECRET_KEY=$SECRET_KEY
DATABASE_URL=sqlite:///$APP_DIR/visadesk.db
FLASK_ENV=production
ADMIN_PASSWORD=$ADMIN_PASS
UPLOAD_FOLDER=$APP_DIR/uploads
ENVEOF

# Create uploads directory
mkdir -p $APP_DIR/uploads

# Initialize database
echo "[8/8] Initializing database..."
export SECRET_KEY=$SECRET_KEY
export DATABASE_URL="sqlite:///$APP_DIR/visadesk.db"
export FLASK_ENV=production
export ADMIN_PASSWORD=$ADMIN_PASS
python3 init_db.py

# Set ownership
chown -R visadesk:visadesk /home/visadesk

# ---- Configure Gunicorn via Supervisor ----
cat > /etc/supervisor/conf.d/visadesk.conf <<SUPEOF
[program:visadesk]
directory=$APP_DIR
command=$APP_DIR/venv/bin/gunicorn wsgi:app --bind 127.0.0.1:9090 --workers 3
user=visadesk
autostart=true
autorestart=true
stopasgroup=true
killasgroup=true
stderr_logfile=/var/log/visadesk/error.log
stdout_logfile=/var/log/visadesk/access.log
environment=
    SECRET_KEY="$SECRET_KEY",
    DATABASE_URL="sqlite:///$APP_DIR/visadesk.db",
    FLASK_ENV="production",
    UPLOAD_FOLDER="$APP_DIR/uploads"
SUPEOF

mkdir -p /var/log/visadesk
chown -R visadesk:visadesk /var/log/visadesk

# ---- Configure Nginx ----
cat > /etc/nginx/sites-available/visadesk <<NGEOF
server {
    listen 80;
    server_name _;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:9090;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120;
    }

    location /static/ {
        alias $APP_DIR/static/;
        expires 30d;
    }
}
NGEOF

# Enable site
ln -sf /etc/nginx/sites-available/visadesk /etc/nginx/sites-enabled/visadesk
rm -f /etc/nginx/sites-enabled/default

# ---- Configure Firewall ----
ufw allow 22
ufw allow 80
ufw allow 443
ufw --force enable

# ---- Start everything ----
supervisorctl reread
supervisorctl update
supervisorctl start visadesk
nginx -t && systemctl restart nginx

echo ""
echo "========================================"
echo "  VisaDesk is LIVE!"
echo "========================================"
echo ""
echo "  Open your browser and go to:"
echo "  http://$(curl -s ifconfig.me)"
echo ""
echo "  Login: admin / $ADMIN_PASS"
echo ""
echo "  Change your admin password after first login!"
echo "========================================"
