# VisaDesk Deployment Guide

## Pre-Deployment Checklist

Before deploying to production, complete these steps:

### 1. Security Configuration

```bash
# Generate a secure SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"
```

Update `.env` or environment variables:
```bash
export FLASK_ENV=production
export SECRET_KEY="your-generated-key-here"
export SESSION_COOKIE_SECURE=True
export SESSION_COOKIE_HTTPONLY=True
```

### 2. Change Default Admin Password

1. Login with admin/admin123
2. Go to user profile → Change Password
3. Set a strong password (16+ characters recommended)
4. NEVER share this password

### 3. Database Backup

```bash
# Before going live, backup the database
cp visadesk.db visadesk.db.backup
```

### 4. Dependency Verification

```bash
pip install -r requirements.txt
pip check  # Verify no conflicts
```

## Local Deployment (Development)

### Windows
```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python seed.py
python app.py
```

### macOS/Linux
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python seed.py
python app.py
```

Visit: http://localhost:5000

## Server Deployment (Production)

### Prerequisites
- Python 3.8+
- pip and virtualenv
- PostgreSQL (recommended) or SQLite
- Nginx (reverse proxy)
- Gunicorn or uWSGI (WSGI server)
- SSL certificate (Let's Encrypt recommended)

### 1. Server Setup (Ubuntu/Debian)

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y python3 python3-pip python3-venv nginx postgresql

# Create application user
sudo useradd -m -s /bin/bash visadesk

# Switch to application user
sudo su - visadesk
```

### 2. Clone Application

```bash
cd /home/visadesk
git clone <your-repo> .
# Or: cp -r visadesk .
```

### 3. Create Virtual Environment

```bash
cd /home/visadesk/visadesk
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn
```

### 4. Configure Application

Create `.env` file:
```bash
cat > .env << 'ENVEND'
FLASK_ENV=production
SECRET_KEY=<your-secure-key>
DATABASE_URL=postgresql://visadesk:password@localhost/visadesk
SESSION_COOKIE_SECURE=True
SESSION_COOKIE_HTTPONLY=True
ENVEND
```

### 5. Initialize Database

```bash
python seed.py
```

### 6. Setup PostgreSQL (Optional)

```bash
# As root or with sudo
sudo -i
su - postgres

# Create database and user
createdb visadesk
createuser visadesk
psql
  ALTER USER visadesk WITH PASSWORD 'secure_password';
  GRANT ALL PRIVILEGES ON DATABASE visadesk TO visadesk;
  \q
exit
```

### 7. Setup Gunicorn Service

Create systemd service file:
```bash
sudo tee /etc/systemd/system/visadesk.service > /dev/null << 'SERVICEEND'
[Unit]
Description=VisaDesk Visa Application Management
After=network.target postgresql.service

[Service]
User=visadesk
WorkingDirectory=/home/visadesk/visadesk
Environment="PATH=/home/visadesk/visadesk/venv/bin"
EnvironmentFile=/home/visadesk/visadesk/.env
ExecStart=/home/visadesk/visadesk/venv/bin/gunicorn \
  --workers 4 \
  --worker-class sync \
  --bind unix:/tmp/visadesk.sock \
  "app:create_app()"
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICEEND
```

Enable and start service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable visadesk
sudo systemctl start visadesk
sudo systemctl status visadesk
```

### 8. Setup Nginx

Create Nginx config:
```bash
sudo tee /etc/nginx/sites-available/visadesk > /dev/null << 'NGINXEND'
server {
    listen 80;
    server_name your-domain.com;

    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL configuration (use Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;

    client_max_body_size 50M;

    location / {
        proxy_pass http://unix:/tmp/visadesk.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
    }

    location /static {
        alias /home/visadesk/visadesk/static;
        expires 30d;
    }

    location /uploads {
        alias /home/visadesk/visadesk/uploads;
        expires 7d;
    }
}
NGINXEND
```

Enable site:
```bash
sudo ln -s /etc/nginx/sites-available/visadesk /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 9. Setup SSL (Let's Encrypt)

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot certonly --nginx -d your-domain.com
```

### 10. Setup Firewall

```bash
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw enable
```

### 11. Backup and Monitoring

Setup automated backups:
```bash
sudo tee /etc/cron.daily/visadesk-backup > /dev/null << 'CRONEND'
#!/bin/bash
BACKUP_DIR="/backups/visadesk"
mkdir -p $BACKUP_DIR
cp /home/visadesk/visadesk/visadesk.db $BACKUP_DIR/visadesk_$(date +%Y%m%d).db
# Keep only last 30 days
find $BACKUP_DIR -name "*.db" -mtime +30 -delete
CRONEND

sudo chmod +x /etc/cron.daily/visadesk-backup
```

Monitor logs:
```bash
# Application logs
sudo journalctl -u visadesk -f

# Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log

# Application error file (if configured)
tail -f /home/visadesk/visadesk/logs/app.log
```

## Database Migrations

### SQLite to PostgreSQL

```bash
# 1. Export data from SQLite
python3 << 'PYEND'
import json
import sqlite3
from datetime import datetime

conn = sqlite3.connect('visadesk.db')
c = conn.cursor()

# Export users
c.execute('SELECT * FROM user')
users = c.fetchall()
# ... (export all tables)

conn.close()
PYEND

# 2. Create PostgreSQL database (done in step 6)

# 3. Update config.py
# DATABASE_URL=postgresql://visadesk:password@localhost/visadesk

# 4. Run migrations
python seed.py

# 5. Import data
# (use SQLAlchemy models to import)
```

## Scaling Considerations

### Horizontal Scaling
```bash
# Use multiple Gunicorn workers
gunicorn --workers 8 --worker-class sync "app:create_app()"

# With worker management
gunicorn --workers 8 --worker-class gevent "app:create_app()"
```

### Load Balancing
Use Nginx upstream:
```nginx
upstream visadesk {
    server 127.0.0.1:8000;
    server 127.0.0.1:8001;
    server 127.0.0.1:8002;
}
```

### Caching
Add Redis for session storage:
```python
# In config.py
SESSION_TYPE = 'redis'
SESSION_REDIS = redis.from_url('redis://localhost:6379')
```

## Monitoring and Alerts

### Health Check
```bash
curl https://your-domain.com/auth/login
# Should return 200 status
```

### Log Analysis
```bash
# Check for errors
grep "ERROR" /var/log/visadesk.log

# Monitor database connections
tail -f /var/log/postgresql/postgresql.log
```

### Uptime Monitoring
Use monitoring service:
- Uptime Robot (free)
- Datadog
- New Relic
- Prometheus

## Troubleshooting

### Application won't start
```bash
# Check logs
sudo journalctl -u visadesk -n 50

# Verify dependencies
source venv/bin/activate
python -c "import flask; import sqlalchemy"

# Test locally
python app.py
```

### Database connection issues
```bash
# Test PostgreSQL
psql -U visadesk -d visadesk -h localhost

# Verify DATABASE_URL
echo $DATABASE_URL
```

### Nginx reverse proxy issues
```bash
# Test Nginx config
sudo nginx -t

# Check permissions
sudo chown -R www-data:www-data /home/visadesk/visadesk/uploads
```

### High memory usage
```bash
# Check Gunicorn workers
ps aux | grep gunicorn

# Reduce workers
gunicorn --workers 2 --worker-class sync "app:create_app()"
```

## Security Hardening

### Application Security
- [x] Change SECRET_KEY
- [x] Change admin password
- [x] Enable HTTPS
- [x] Set secure cookies
- [x] Use strong session timeout
- [ ] Add rate limiting
- [ ] Add two-factor authentication
- [ ] Enable audit logging

### System Security
- [x] Firewall enabled
- [x] SSH key authentication
- [x] Regular updates
- [ ] Intrusion detection (fail2ban)
- [ ] SELinux/AppArmor
- [ ] Regular backups

### Database Security
- [x] Strong database password
- [x] PostgreSQL over SQLite (production)
- [ ] Connection pooling
- [ ] Regular backups
- [ ] Encryption at rest

## Rollback Plan

If deployment fails:

```bash
# 1. Stop application
sudo systemctl stop visadesk

# 2. Restore previous version
cd /home/visadesk
git revert <commit-hash>
# OR restore from backup
cp visadesk.backup.tar.gz . && tar -xzf visadesk.backup.tar.gz

# 3. Restore database
cp /backups/visadesk/visadesk.db .

# 4. Restart application
sudo systemctl start visadesk

# 5. Verify
curl https://your-domain.com/auth/login
```

## Performance Tuning

### Database
```python
# In config.py
SQLALCHEMY_ECHO = False  # Disable SQL logging
SQLALCHEMY_POOL_SIZE = 20
SQLALCHEMY_POOL_RECYCLE = 3600
```

### Caching
```python
from flask_caching import Cache
cache = Cache(app, config={'CACHE_TYPE': 'redis'})
```

### Static Files
```nginx
# In Nginx
expires 30d;
add_header Cache-Control "public, immutable";
```

## Support and Maintenance

- Check application logs regularly
- Monitor resource usage (CPU, memory, disk)
- Update dependencies monthly
- Test backups quarterly
- Review user access logs weekly
- Scale as needed based on usage

## Contact Information

For deployment issues or questions:
- Check logs first
- Review this guide
- Contact development team
- File issue on GitHub

---

Last Updated: April 2026
Version: 1.0.0
