# Database Restart and Recovery SOP

**Category:** database  
**Owner:** DBA Team  
**Last Updated:** 2024-01-15

## Purpose
Procedures for diagnosing and recovering PostgreSQL database issues in production.

## 1. Connection Timeout / Max Connections

**Symptoms:** Applications report `FATAL: remaining connection slots are reserved`, queries timeout.

**Steps:**
1. Check current connections: `SELECT count(*), state FROM pg_stat_activity GROUP BY state;`
2. Identify idle connections: `SELECT pid, usename, application_name, state, query_start FROM pg_stat_activity WHERE state = 'idle' ORDER BY query_start;`
3. Terminate old idle connections: `SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND query_start < now() - interval '10 minutes';`
4. If issue persists, increase `max_connections` in `postgresql.conf` and restart.
5. Long-term: implement connection pooling with PgBouncer.

## 2. Database Restart Procedure

**Pre-requisites:** Notify #ops-alerts before starting. Get approval from on-call manager.

**Steps:**
1. Notify: Post in #ops-alerts "Starting DB maintenance on `<hostname>`"
2. Check active transactions: `SELECT count(*) FROM pg_stat_activity WHERE state = 'active';`
3. Wait for active transactions to complete or terminate if blocking maintenance.
4. Stop PostgreSQL gracefully: `sudo systemctl stop postgresql`
5. Wait 30 seconds.
6. Start: `sudo systemctl start postgresql`
7. Verify: `sudo systemctl status postgresql`
8. Test connection: `psql -U postgres -c "SELECT version();"`
9. Notify #ops-alerts: "DB maintenance complete on `<hostname>`"

## 3. High Disk Usage

**Symptoms:** Alerts for >85% disk usage on database host.

**Steps:**
1. Check usage: `df -h /var/lib/postgresql/`
2. Find large files: `du -sh /var/lib/postgresql/data/pg_wal/*`
3. Archive old WAL logs to S3: `aws s3 sync /var/lib/postgresql/wal-archive/ s3://backups/wal/`
4. Delete archived WAL: `pg_archivecleanup /var/lib/postgresql/data/pg_wal/ <latest_wal>`
5. Compress old log files: `gzip /var/log/postgresql/postgresql-*.log`
6. Monitor: `watch -n 60 df -h`
