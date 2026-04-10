# Network & VPN Troubleshooting SOP

**Category:** network  
**Owner:** Network Team  
**Last Updated:** 2024-02-20

## 1. VPN Connectivity Issues

**Symptoms:** Remote users unable to connect to VPN; connection refused or timeout.

**Steps:**
1. Verify VPN service status: `sudo systemctl status openvpn@server`
2. Check VPN server logs: `journalctl -u openvpn --since "2 hours ago" | tail -100`
3. Verify the VPN gateway is reachable: `ping -c 4 <vpn-gateway-ip>`
4. Check firewall rules: `sudo iptables -L INPUT -v -n | grep 1194`
5. If firewall was recently changed, diff against last known good:
   `git -C /etc/firewall diff HEAD~1 HEAD`
6. Roll back if needed: `git -C /etc/firewall checkout HEAD~1 -- rules.v4 && iptables-restore < /etc/firewall/rules.v4`
7. Test VPN connectivity from a test client.
8. Notify affected users via email once resolved.

## 2. DNS Resolution Failures

**Symptoms:** Internal hostnames not resolving; services failing to connect to each other.

**Steps:**
1. Test DNS: `nslookup <internal-hostname> <dns-server-ip>`
2. Check DNS server status: `sudo systemctl status bind9` (or `named`)
3. Review DNS logs: `journalctl -u named --since "1 hour ago"`
4. Flush DNS cache on affected hosts: `sudo systemd-resolve --flush-caches`
5. If DNS server is down, fail over to secondary: update `/etc/resolv.conf` to point to backup NS.

## 3. High Network Latency / Packet Loss

**Steps:**
1. Run traceroute: `traceroute -n <destination>`
2. Check interface errors: `ip -s link show eth0`
3. Monitor real-time traffic: `iftop -i eth0`
4. Identify top talkers: `nethogs eth0`
5. If a misconfigured host is flooding: isolate with firewall drop rule, then investigate.
