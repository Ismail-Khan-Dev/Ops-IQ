# Deployment Guide

This guide covers deploying OpsIQ to various environments.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Local Development](#local-development)
3. [Docker Deployment](#docker-deployment)
4. [AWS Deployment](#aws-deployment)
5. [Kubernetes Deployment](#kubernetes-deployment)
6. [Environment Configuration](#environment-configuration)
7. [Database Setup](#database-setup)
8. [Monitoring Setup](#monitoring-setup)
9. [Security Checklist](#security-checklist)
10. [Troubleshooting](#troubleshooting)

## Prerequisites

### System Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 2 cores | 4 cores |
| RAM | 4GB | 8GB |
| Storage | 20GB | 50GB |
| OS | Ubuntu 20.04+ | Ubuntu 22.04 LTS |

### Software Requirements

- Docker 24.0+
- Docker Compose 2.20+
- Python 3.11+
- PostgreSQL 16+
- Redis 7+
- Nginx 1.24+

### API Keys Required

- OpenAI API Key (for LLM agents)
- Shopify API Credentials (for e-commerce integration)
- Langfuse API Keys (for observability)

## Local Development

### Quick Start

```bash
# Clone repository
git clone https://github.com/Ismail-2001/ecom-ops-automation-system.git
cd ecom-ops-automation-system

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env

# Edit .env with your API keys
nano .env

# Start development server
uvicorn ecommerce_ops.api.app:app --reload --host 0.0.0.0 --port 8000
```

### Database Setup

```bash
# Start PostgreSQL (using Docker)
docker run -d \
  --name eops-postgres \
  -e POSTGRES_USER=dev \
  -e POSTGRES_PASSWORD=dev_secret \
  -e POSTGRES_DB=ecommerce_ops \
  -p 5432:5432 \
  postgres:16-alpine

# Run migrations
alembic upgrade head

# Seed demo data
python -m ecommerce_ops.demo.seed
```

## Docker Deployment

### Production Deployment

```bash
# Copy environment file
cp .env.example .env

# Edit .env with production values
nano .env

# Build and start services
docker compose up -d --build

# Verify services
docker compose ps

# Check logs
docker compose logs -f app
```

### Docker Compose Services

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| app | Custom | 8000 | FastAPI application |
| postgres | postgres:16-alpine | 5432 | Database |
| redis | redis:7-alpine | 6379 | Cache |
| nginx | nginx:alpine | 80, 443 | Reverse proxy |
| prometheus | prom/prometheus | 9090 | Metrics |
| grafana | grafana/grafana | 3000 | Dashboards |
| alertmanager | prom/alertmanager | 9093 | Alerts |

### Production Docker Compose

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    environment:
      - ENV=production
      - DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/ecommerce_ops
      - REDIS_URL=redis://redis:6379/0
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 1G
        reservations:
          cpus: '1'
          memory: 512M
    restart: unless-stopped

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: user
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: ecommerce_ops
    volumes:
      - postgres_data:/var/lib/postgresql/data
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 2G
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes --maxmemory 512mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
```

## AWS Deployment

### Architecture

```
                    ┌─────────────┐
                    │    ALB      │
                    │  (Load Balancer) │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────▼─────┐ ┌────▼────┐ ┌────▼────┐
        │   ECS     │ │   ECS   │ │   ECS   │
        │ Container │ │Container│ │Container│
        └─────┬─────┘ └────┬────┘ └────┬────┘
              │            │            │
              └────────────┼────────────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────▼─────┐ ┌────▼────┐ ┌────▼────┐
        │  RDS      │ │ElastiCache│ │   S3   │
        │(PostgreSQL)│ │ (Redis) │ │(Storage)│
        └───────────┘ └─────────┘ └─────────┘
```

### ECS Deployment

```bash
# Create ECR repository
aws ecr create-repository --repository-name eops-app

# Build and push Docker image
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com
docker build -t eops-app .
docker tag eops-app:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/eops-app:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/eops-app:latest

# Create ECS cluster
aws ecs create-cluster --cluster-name eops-cluster

# Register task definition
aws ecs register-task-definition --cli-input-json file://task-definition.json

# Create service
aws ecs create-service \
  --cluster eops-cluster \
  --service-name eops-service \
  --task-definition eops-app:1 \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}"
```

### RDS Setup

```bash
# Create RDS instance
aws rds create-db-instance \
  --db-instance-identifier eops-db \
  --db-instance-class db.t3.medium \
  --engine postgres \
  --engine-version 16 \
  --master-username admin \
  --master-user-password ${DB_PASSWORD} \
  --allocated-storage 20 \
  --storage-type gp3 \
  --vpc-security-group-ids sg-xxx \
  --db-subnet-group-name eops-subnet-group \
  --backup-retention-period 7 \
  --multi-az \
  --storage-encrypted
```

### ElastiCache Setup

```bash
# Create Redis cluster
aws elasticache create-cache-cluster \
  --cache-cluster-id eops-redis \
  --cache-node-type cache.t3.medium \
  --engine redis \
  --engine-version 7.0 \
  --num-cache-nodes 1 \
  --vpc-security-group-ids sg-xxx \
  --cache-subnet-group-name eops-redis-subnet
```

## Kubernetes Deployment

### Helm Chart

```yaml
# helm/values.yaml
replicaCount: 2

image:
  repository: <account-id>.dkr.ecr.us-east-1.amazonaws.com/eops-app
  tag: latest
  pullPolicy: Always

service:
  type: ClusterIP
  port: 8000

ingress:
  enabled: true
  className: nginx
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
  hosts:
    - host: app.opsiq.ai
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: app-tls
      hosts:
        - app.opsiq.ai

resources:
  limits:
    cpu: 2
    memory: 1Gi
  requests:
    cpu: 1
    memory: 512Mi

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
  targetMemoryUtilizationPercentage: 80
```

### Deploy with Helm

```bash
# Add Helm repos
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts

# Install monitoring
helm install prometheus prometheus-community/prometheus
helm install grafana grafana/grafana

# Deploy application
helm install eops-app ./helm
```

## Environment Configuration

### Required Variables

```bash
# Application
ENV=production
PROJECT_NAME=OpsIQ
SECRET_KEY=your-secret-key

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/ecommerce_ops
DB_PASSWORD=your-db-password

# Redis
REDIS_URL=redis://host:6379/0

# Shopify
SHOPIFY_CLIENT_ID=your-client-id
SHOPIFY_CLIENT_SECRET=your-client-secret
SHOPIFY_APP_URL=https://your-app.com
SHOPIFY_SHOP_DOMAIN=your-store.myshopify.com
SHOPIFY_ACCESS_TOKEN=your-access-token

# OpenAI
OPENAI_API_KEY=your-openai-key

# Security
JWT_SECRET_KEY=your-jwt-secret
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=30

# Observability
LANGFUSE_PUBLIC_KEY=your-public-key
LANGFUSE_SECRET_KEY=your-secret-key
LANGFUSE_HOST=https://cloud.langfuse.com
```

### Optional Variables

```bash
# Monitoring
PROMETHEUS_PORT=9090
GRAFANA_PORT=3000
ALERTMANAGER_PORT=9093

# Rate Limiting
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_PER_HOUR=1000

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

## Database Setup

### Initial Setup

```bash
# Connect to PostgreSQL
psql -h localhost -U user -d ecommerce_ops

# Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

# Run migrations
alembic upgrade head

# Seed data
python -m ecommerce_ops.demo.seed
```

### Backup Strategy

```bash
# Automated backup script
#!/bin/bash
BACKUP_DIR="/backups/postgres"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/ecommerce_ops_$DATE.sql"

# Create backup
pg_dump -h localhost -U user ecommerce_ops > $BACKUP_FILE

# Compress
gzip $BACKUP_FILE

# Upload to S3
aws s3 cp $BACKUP_FILE.gz s3://eops-backups/postgres/

# Cleanup old backups (keep 30 days)
find $BACKUP_DIR -name "*.sql.gz" -mtime +30 -delete
```

### Restore

```bash
# Download backup
aws s3 cp s3://eops-backups/postgres/ecommerce_ops_20251220_120000.sql.gz .

# Decompress
gunzip ecommerce_ops_20251220_120000.sql.gz

# Restore
psql -h localhost -U user ecommerce_ops < ecommerce_ops_20251220_120000.sql
```

## Monitoring Setup

### Prometheus Configuration

```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'eops-app'
    static_configs:
      - targets: ['app:8000']
    metrics_path: '/metrics'

  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres-exporter:9187']

  - job_name: 'redis'
    static_configs:
      - targets: ['redis-exporter:9121']
```

### Alert Rules

```yaml
# alert_rules.yml
groups:
  - name: eops-alerts
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: High error rate detected

      - alert: HighLatency
        expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 0.5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: High latency detected

      - alert: LowMemory
        expr: node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes < 0.2
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: Low memory available
```

## Deployment Strategies

### Stop/Start with Auto-Rollback (current CI)

The `.github/workflows/cd.yml` workflow deploys on tag push by stopping the old
`api` container, running `alembic upgrade head`, and starting the new image.
If the readiness probe (`/ready`, DB-checking) does not return `200` within
30 seconds, the workflow restores the previous image and fails — so a broken
release never stays live.

This is the default and simplest strategy. It causes a brief downtime window
during the stop/start swap.

### Rolling Update (minimal downtime)

For near-zero-downtime updates, use a rolling recreate instead of stop/start:

```bash
docker compose up -d --no-deps --build --scale api=2 api
```

The `/ready` probe (DB-aware) gates traffic, and uvicorn's
`--timeout-graceful-shutdown 30` (set in `Dockerfile` and
`docker-compose.yml`) gives in-flight requests 30s to finish before the old
replica is torn down. Verify health before shrinking back:

```bash
curl -sf http://localhost:8000/ready && docker compose up -d --no-deps --scale api=1 api
```

### Blue-Green / Zero-Downtime

True zero-downtime blue-green requires a load balancer (e.g. Nginx upstream or
an ALB) fronting two full stacks, swapping traffic only after `/ready` passes on
the new stack. OpsIQ containers are stateless and image-pinned, so this is
straightforward once a second stack or dynamic upstream is provisioned — but it
is **not** what the default CI workflow does today.

### Guidelines

- Always run `alembic upgrade head` before starting the new image (the compose
  `api` command already does this).
- Only route traffic once `/ready` returns `200`; `/live` only proves the
  process is up, not that the DB is reachable.
- Use `--timeout-graceful-shutdown` on uvicorn so WebSocket hangs and queued
  tasks are drained by the lifespan shutdown handler.

## Security Checklist

### Pre-Deployment

- [ ] All secrets in environment variables (not in code)
- [ ] JWT secret is strong and random
- [ ] Database password is strong
- [ ] API keys are rotated regularly
- [ ] HTTPS enabled for all endpoints
- [ ] CORS configured properly
- [ ] Rate limiting enabled
- [ ] Input validation on all endpoints
- [ ] SQL injection protection (SQLAlchemy)
- [ ] XSS protection (security headers)
- [ ] CSRF protection enabled
- [ ] Audit logging enabled
- [ ] RBAC configured
- [ ] MFA enabled for admin accounts

### Network Security

- [ ] Firewall configured
- [ ] Only necessary ports exposed
- [ ] VPC configured (if AWS)
- [ ] Security groups restrict access
- [ ] Database not publicly accessible
- [ ] Redis not publicly accessible

### Monitoring

- [ ] Prometheus scraping metrics
- [ ] Grafana dashboards configured
- [ ] Alertmanager routing alerts
- [ ] Log aggregation configured
- [ ] Error tracking enabled
- [ ] Uptime monitoring enabled

## Troubleshooting

### Common Issues

#### Application Won't Start

```bash
# Check logs
docker compose logs app

# Common causes:
# 1. Missing environment variables
# 2. Database connection failed
# 3. Redis connection failed
# 4. Port already in use

# Solutions:
# 1. Verify .env file exists and has all required variables
# 2. Check PostgreSQL is running and accessible
# 3. Check Redis is running and accessible
# 4. Change port in docker-compose.yml
```

#### Database Connection Failed

```bash
# Check PostgreSQL status
docker compose ps postgres

# Test connection
psql -h localhost -U user -d ecommerce_ops

# Common causes:
# 1. PostgreSQL not running
# 2. Wrong credentials
# 3. Network issues
# 4. Firewall blocking

# Solutions:
# 1. Start PostgreSQL: docker compose up -d postgres
# 2. Verify credentials in .env
# 3. Check network configuration
# 4. Check firewall rules
```

#### High Memory Usage

```bash
# Check memory usage
docker stats

# Common causes:
# 1. Memory leak
# 2. Large cache
# 3. Too many connections

# Solutions:
# 1. Restart application: docker compose restart app
# 2. Clear Redis cache: redis-cli FLUSHALL
# 3. Reduce connection pool size
```

#### High CPU Usage

```bash
# Check CPU usage
docker stats

# Common causes:
# 1. Infinite loop
# 2. Heavy computation
# 3. Too many requests

# Solutions:
# 1. Check application logs for errors
# 2. Scale horizontally: docker compose up -d --scale app=3
# 3. Implement rate limiting
```

### Health Checks

```bash
# Application health
curl http://localhost:8000/health

# Database health
docker compose exec postgres pg_isready

# Redis health
docker compose exec redis redis-cli ping

# Prometheus health
curl http://localhost:9090/-/healthy

# Grafana health
curl http://localhost:3000/api/health
```

### Logs

```bash
# Application logs
docker compose logs -f app

# PostgreSQL logs
docker compose logs -f postgres

# Redis logs
docker compose logs -f redis

# Nginx logs
docker compose logs -f nginx

# All logs
docker compose logs -f
```

## Support

For issues not covered in this guide:

1. Check the [FAQ](FAQ.md)
2. Search [GitHub Issues](https://github.com/Ismail-2001/ecom-ops-automation-system/issues)
3. Create a new issue with:
   - Environment details
   - Steps to reproduce
   - Error messages
   - Logs
