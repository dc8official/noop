# LNMP v3.1.0 — Disaster Recovery & Database Restoration Runbook

This runbook describes the standard operating procedures for restoring the LNMP v3.1.0 database and application environment from timestamped backups.

---

## 1. Backup File Locations

Automated pre-upgrade and decommissioning backups are generated in plaintext SQL format at:
```bash
/var/backups/netmon/netmon_backup_<YYYYMMDD_HHMMSS>.sql
```

To list available backups sorted by date:
```bash
ls -lht /var/backups/netmon/
```

---

## 2. Prerequisites Before Restoration

1. Ensure the PostgreSQL and TimescaleDB server services are active:
   ```bash
   sudo systemctl status postgresql
   ```
2. Stop the monitoring engine and API daemons to prevent write contention during data restoration:
   ```bash
   sudo systemctl stop netmon-engine netmon-api
   ```
3. Load database credentials from the environment file:
   ```bash
   set -a
   source /etc/netmon/netmon.env
   set +a
   ```

---

## 3. Database Restoration Procedure

### Step 1: Re-create Clean Database Target (Optional / Clean Restore)
If performing a full database rebuild:
```bash
PGPASSWORD="${NETMON_DB_PASSWORD}" psql -h "${NETMON_DB_HOST:-127.0.0.1}" -U "${NETMON_DB_USER:-netmon_user}" -d postgres -c "DROP DATABASE IF EXISTS netmon;"
PGPASSWORD="${NETMON_DB_PASSWORD}" psql -h "${NETMON_DB_HOST:-127.0.0.1}" -U "${NETMON_DB_USER:-netmon_user}" -d postgres -c "CREATE DATABASE netmon;"
PGPASSWORD="${NETMON_DB_PASSWORD}" psql -h "${NETMON_DB_HOST:-127.0.0.1}" -U "${NETMON_DB_USER:-netmon_user}" -d netmon -c "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;"
```

### Step 2: Ingest Backup SQL Dump
```bash
RESTORE_FILE="/var/backups/netmon/netmon_backup_YYYYMMDD_HHMMSS.sql"

PGPASSWORD="${NETMON_DB_PASSWORD}" psql \
  -h "${NETMON_DB_HOST:-127.0.0.1}" \
  -p "${NETMON_DB_PORT:-5432}" \
  -U "${NETMON_DB_USER:-netmon_user}" \
  -d "${NETMON_DB_NAME:-netmon}" \
  -f "${RESTORE_FILE}"
```

### Step 3: Run Forward Alembic Migrations
Ensure all schema tables, views, and continuous aggregates are up to date:
```bash
cd /opt/netmon/noop/backend
PYTHONPATH=/opt/netmon/noop:/opt/netmon/noop/backend /opt/netmon/venv/bin/alembic -c alembic.ini upgrade head
```

### Step 4: Flush Redis Session Cache (If Redis Acceleration is Active)
If using the Redis storage driver, flush stale session keys:
```bash
redis-cli flushdb
```

### Step 5: Restart LNMP Daemons
```bash
sudo systemctl restart redis-server || sudo systemctl restart redis || true
sudo systemctl restart netmon-api netmon-engine nginx
```

### Step 6: Verify Service Health
```bash
curl -s http://127.0.0.1:8000/api/v1/health | jq .
curl -s http://127.0.0.1:8000/api/v1/version | jq .
```
Expected response:
```json
{
  "status": "ok",
  "version": "3.1.0"
}
```
