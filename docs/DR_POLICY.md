# OpsIQ — Disaster Recovery Policy

## RTO / RPO Targets

| Service        | RTO (Recovery Time) | RPO (Data Loss) | Strategy                        |
|----------------|---------------------|------------------|---------------------------------|
| API Server     | 5 minutes           | 0 (on restart)   | Image-pinned restart + auto-rollback on failed /ready probe |
| PostgreSQL     | 15 minutes          | 1 hour           | WAL archiving + hourly pg_dump  |
| Redis Cache    | 5 minutes           | 0 (ephemeral)    | Rebuild from DB on cold start   |
| Frontend       | 2 minutes           | 0 (static)       | CDN + instant rollback          |
| Alertmanager   | 10 minutes          | 0 (stateless)    | Config-as-code redeploy         |

## Backup Schedule

| Backup Type       | Frequency  | Retention | Storage              |
|-------------------|------------|-----------|----------------------|
| PostgreSQL dump   | Hourly     | 7 days    | Local + S3/GCS (IA)  |
| PostgreSQL WAL     | Continuous | 7 days    | Local archive         |
| Redis BGSAVE      | On deploy  | 1 copy    | Local                 |
| Config snapshots  | On deploy  | 10 copies | Local                 |

## Recovery Procedures

### API Server Failure
1. Alertmanager fires `APIDown` → PagerDuty + Slack
2. Run `./scripts/deploy.sh rollback` to revert to last healthy image
3. If rollback fails: `./scripts/deploy.sh down && ./scripts/deploy.sh up`
4. Verify: `curl http://localhost:8000/health`

### Database Corruption
1. Stop API: `docker compose stop api`
2. Restore from latest backup:
   ```bash
   gunzip -c backups/<timestamp>/postgres.sql.gz | \
     docker exec -i opsiq-postgres psql -U postgres ecommerce_ops
   ```
3. Start API: `docker compose start api`
4. Verify data integrity via dashboard

### Full Stack Recovery
1. Clone repo on fresh host
2. Copy `.env.docker` and `docker-compose.yml`
3. Run `./scripts/deploy.sh up`
4. Restore database from offsite backup if needed
5. Verify all services healthy

## Escalation Contacts

| Severity | Response Time | Contact Channel |
|----------|--------------|-----------------|
| Critical | 5 minutes    | PagerDuty       |
| Warning  | 30 minutes   | Slack #opsiq-warnings |
| Info     | Next business day | Email      |

## Post-Incident

1. Create incident report within 24 hours
2. Update runbook with lessons learned
3. Review and adjust RTO/RPO if breach occurred
4. Schedule blameless retrospective for P0/P1 incidents
