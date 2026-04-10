# Database Restart SOP

**Category:** database  
**Last Updated:** 2024-01-15

## Purpose
Procedure for safely restarting PostgreSQL database instances in production.

## Prerequisites
- SSH access to the database host
- sudo privileges
- Notify #ops-alerts channel before starting

## Steps

1. Check current connections: `SELECT count(*) FROM pg_stat_activity;`
2. Notify stakeholders in #ops-alerts: "Starting planned DB maintenance"
3. Set application to maintenance mode if possible
4. Gracefully stop PostgreSQL: `sudo systemctl stop postgresql`
5. Wait 30 seconds for processes to terminate
6. Start PostgreSQL: `sudo systemctl start postgresql`
7. Verify service is healthy: `sudo systemctl status postgresql`
8. Test connectivity: `psql -U postgres -c '\l'`
9. Notify stakeholders that maintenance is complete

## Rollback
If restart fails, check `/var/log/postgresql/` for errors and escalate to DBA team.

---

# VPN Troubleshooting SOP

**Category:** network  
**Last Updated:** 2024-02-20

## Purpose
Steps for diagnosing and resolving VPN connectivity issues.

## Steps

1. Verify VPN server status via monitoring dashboard
2. Check firewall rules: `sudo iptables -L | grep vpn`
3. Review VPN server logs: `journalctl -u openvpn --since "1 hour ago"`
4. Test connectivity to VPN gateway: `ping <vpn-gateway-ip>`
5. If firewall was recently updated, compare current rules to last known good config in Git
6. Roll back firewall config if change is the root cause
7. Notify affected users via email once resolved

---

# Email Service Recovery SOP

**Category:** email  
**Last Updated:** 2024-03-01

## Purpose
Procedure for recovering the SMTP email service when it is unresponsive.

## Steps

1. Check SMTP server status: `sudo systemctl status postfix`
2. Review mail queue: `mailq`
3. Check available disk space (full disk is a common cause): `df -h`
4. If disk is full, archive old mail logs: `gzip /var/log/mail.log.1`
5. Restart SMTP service: `sudo systemctl restart postfix`
6. Send a test email: `echo "Test" | mail -s "SMTP Test" ops@company.com`
7. Monitor queue drain: `watch mailq`
