# Infrastructure & Service Recovery SOP

**Category:** infrastructure  
**Owner:** Platform Team  
**Last Updated:** 2024-03-01

## 1. High CPU Usage on Application Servers

**Symptoms:** CPU > 90% sustained, response times > 2s, alerts firing.

**Steps:**
1. Identify top processes: `top -b -n 1 | head -20` or `ps aux --sort=-%cpu | head -10`
2. Check for runaway cron jobs: `crontab -l && cat /etc/cron.d/*`
3. Profile the top process: `strace -p <pid> -e trace=all -c`
4. If cron job is the culprit: `kill -9 <pid>` and disable the cron entry.
5. Check for memory pressure causing swapping: `vmstat 1 5`
6. Scale horizontally if CPU is legitimately high: add nodes to load balancer pool.
7. Add a CPU alert at 80% threshold if not present.

## 2. SSL Certificate Expiry

**Symptoms:** Browser security warnings, HTTPS requests failing with cert error.

**Steps:**
1. Check expiry: `echo | openssl s_client -connect <hostname>:443 2>/dev/null | openssl x509 -noout -dates`
2. If using Let's Encrypt: `sudo certbot renew --force-renewal`
3. Reload web server: `sudo systemctl reload nginx` (or `apache2`)
4. Verify renewal: re-run step 1 and confirm new expiry date.
5. Ensure auto-renewal cron/timer is active: `systemctl status certbot.timer`
6. Add monitoring for cert expiry < 30 days.

## 3. Deployment Rollback

**Symptoms:** New deploy causes errors; need to revert to previous version.

**Steps:**
1. Identify last stable version from deployment history.
2. Kubernetes: `kubectl rollout undo deployment/<name> -n <namespace>`
3. Verify rollback: `kubectl rollout status deployment/<name>`
4. Check application health: `curl -s https://<app>/health | jq .`
5. Document the incident in the incident log.
6. Create a post-mortem ticket for the failed deployment.

## 4. Email / SMTP Service Recovery

**Symptoms:** No outbound email, SMTP connection refused, growing mail queue.

**Steps:**
1. Check service: `sudo systemctl status postfix`
2. Review queue: `mailq | tail -20`
3. Check disk space (full disk is common cause): `df -h /var/spool/postfix/`
4. Free disk if needed: `gzip /var/log/mail.log.1 && find /var/log -name "*.gz" -mtime +30 -delete`
5. Restart: `sudo systemctl restart postfix`
6. Test: `echo "Test body" | mail -s "SMTP Recovery Test" ops@company.com`
7. Monitor queue drain: `watch -n 10 mailq`
