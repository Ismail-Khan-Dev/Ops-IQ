# Deploying OpsIQ on Hostinger VPS

## Prerequisites
- Hostinger VPS (any plan — Ubuntu 22.04 recommended)
- Domain name pointed to your VPS IP
- SSH access to the server

## Step-by-Step Deployment

---

### 1. SSH into Your VPS

```bash
ssh root@your-server-ip
```

(Replace `your-server-ip` with your VPS IP from Hostinger hPanel)

---

### 2. Install Dependencies

```bash
# Update system
apt update && apt upgrade -y

# Install Python 3.11
apt install -y software-properties-common
add-apt-repository ppa:deadsnakes/ppa -y
apt install -y python3.11 python3.11-venv python3.11-dev

# Install other tools
apt install -y git nginx supervisor curl redis-server postgresql postgresql-contrib

# Install Node.js 20 for frontend
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs

# Install Playwright dependencies
apt install -y libnss3 libnspr4 libatk-bridge2.0-0 libdrm2 libxkbcommon0 libgbm1
```

---

### 3. Setup PostgreSQL

```bash
# Start PostgreSQL
systemctl start postgresql
systemctl enable postgresql

# Create database and user
sudo -u postgres psql -c "CREATE DATABASE ecommerce_ops;"
sudo -u postgres psql -c "CREATE USER ecom_user WITH PASSWORD 'your_strong_password';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE ecommerce_ops TO ecom_user;"
```

---

### 4. Setup Redis

```bash
systemctl start redis-server
systemctl enable redis-server
```

---

### 5. Clone the Repository

```bash
cd /opt
git clone https://github.com/Ismail-2001/ecom-ops-automation-system.git
cd ecom-ops-automation-system
```

---

### 6. Setup Backend

```bash
# Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install gunicorn

# Install Playwright browsers
playwright install chromium
```

---

### 7. Environment Configuration

```bash
# Create .env file
nano .env
```

Paste this (update with your actual values):

```ini
ENV=production
DEBUG=false

# LLM (use any one)
GOOGLE_API_KEY=your_google_api_key
# DEEPSEEK_API_KEY=your_deepseek_key

# Database
DATABASE_URL=postgresql+asyncpg://ecom_user:your_strong_password@localhost:5432/ecommerce_ops

# Redis
REDIS_URL=redis://localhost:6379/0

# Shopify
SHOPIFY_API_KEY=your_shopify_api_key
SHOPIFY_PASSWORD=your_shopify_admin_api_access_token
SHOPIFY_STORE_URL=https://your-store.myshopify.com
SHOPIFY_API_VERSION=2024-01

# Safety
SHADOW_MODE=true
GLOBAL_PO_LIMIT=1000.0
GLOBAL_PRICE_CHANGE_LIMIT_PERCENT=20.0

# Rate Limiting
RATE_LIMIT_PER_MINUTE=60

# Slack (optional)
SLACK_BOT_TOKEN=
SLACK_CHANNEL=
```

Save: `Ctrl+X`, then `Y`, then `Enter`

---

### 8. Setup Supervisor (Process Manager)

```bash
nano /etc/supervisor/conf.d/opsiq.conf
```

Paste:

```ini
[program:opsiq]
command=/opt/ecom-ops-automation-system/.venv/bin/gunicorn -w 4 -k uvicorn.workers.UvicornWorker ecommerce_ops.api.app:app --bind 127.0.0.1:8000 --timeout 120
directory=/opt/ecom-ops-automation-system
user=root
autostart=true
autorestart=true
stopasgroup=true
killasgroup=true
stderr_logfile=/var/log/opsiq.err.log
stdout_logfile=/var/log/opsiq.out.log
```

Save and enable:

```bash
supervisorctl reread
supervisorctl update
supervisorctl start opsiq
supervisorctl status opsiq   # Should show RUNNING
```

---

### 9. Setup Nginx Reverse Proxy

```bash
nano /etc/nginx/sites-available/opsiq
```

Paste (replace `your-domain.com` with your actual domain):

```nginx
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }

    location /ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }

    location /static {
        alias /opt/ecom-ops-automation-system/dashboard/dist;
        expires 30d;
    }
}
```

Enable the site:

```bash
ln -s /etc/nginx/sites-available/opsiq /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default  # Remove default
nginx -t                                  # Test config
systemctl restart nginx
```

---

### 10. SSL Certificate (HTTPS)

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d your-domain.com -d www.your-domain.com
```

Follow the prompts. Certbot auto-configures HTTPS and sets up auto-renewal.

---

### 11. Build & Deploy Frontend

```bash
cd /opt/ecom-ops-automation-system/dashboard
npm install
npm run build
```

The built files are in `dashboard/dist/` — Nginx already serves them at `/static`.

---

### 12. Run Database Migrations

```bash
cd /opt/ecom-ops-automation-system
source .venv/bin/activate
alembic upgrade head
```

---

### 13. Verify Deployment

```bash
# Check backend health
curl http://127.0.0.1:8000/health

# Check supervisor
supervisorctl status opsiq

# Check nginx
systemctl status nginx
```

Open `https://your-domain.com` in your browser.

---

### 14. Monitoring & Logs

```bash
# Backend logs
tail -f /var/log/opsiq.out.log
tail -f /var/log/opsiq.err.log

# Nginx logs
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log

# Restart backend (after config changes)
supervisorctl restart opsiq
```

---

### Quick Commands Reference

| Action | Command |
|:---|---:|
| Restart backend | `supervisorctl restart opsiq` |
| View backend logs | `tail -f /var/log/opsiq.out.log` |
| Restart Nginx | `systemctl restart nginx` |
| Renew SSL | `certbot renew` |
| Deploy updates | `cd /opt/ecom-ops-automation-system && git pull && supervisorctl restart opsiq` |

---

### 15. Rollback Plan

#### A. Code Rollback

```bash
# Roll back to previous commit
cd /opt/ecom-ops-automation-system
git log --oneline -5              # See recent commits
git reset --hard <previous-sha>   # Roll back to known-good commit
supervisorctl restart opsiq       # Restart backend
npm run build                     # Rebuild frontend if changed
```

#### B. Database Rollback

```bash
# Alembic downgrade (go back one migration)
cd /opt/ecom-ops-automation-system
source .venv/bin/activate
alembic downgrade -1

# Or go to a specific revision
alembic downgrade <revision_id>
```

#### C. Full System Rollback (disaster recovery)

```bash
# Stop services
supervisorctl stop opsiq
systemctl stop nginx

# Restore database from backup
sudo -u postgres psql -c "DROP DATABASE ecommerce_ops;"
sudo -u postgres psql -c "CREATE DATABASE ecommerce_ops WITH OWNER ecom_user;"
sudo -u postgres pg_restore -d ecommerce_ops /var/backups/opsiq/opsiq_$(date +%Y%m%d).dump

# Checkout known-good tag
cd /opt/ecom-ops-automation-system
git checkout tags/v1.0.0   # or a known-good commit

# Restart
supervisorctl start opsiq
systemctl start nginx
```

#### D. Backup Checklist (set up before production)

```bash
# Create backup directory
mkdir -p /var/backups/opsiq

# Daily database backup cron
echo "0 3 * * * root pg_dump -U ecom_user ecommerce_ops > /var/backups/opsiq/opsiq_\$(date +\%Y\%m\%d).dump" > /etc/cron.d/opsiq-backup

# Keep last 7 days of backups
echo "0 5 * * * root find /var/backups/opsiq -mtime +7 -delete" >> /etc/cron.d/opsiq-backup
```

---

## Domain Setup (Hostinger DNS)

1. Go to **Hostinger hPanel → Domains → DNS Zone**
2. Add these records:

| Type | Name | Value |
|:---|---:|---:|
| A | `@` | `your-vps-ip-address` |
| A | `www` | `your-vps-ip-address` |

3. Wait 5-30 minutes for DNS propagation
4. Then run `certbot` from Step 10

---

Done. Your OpsIQ instance is now live at `https://your-domain.com`.
