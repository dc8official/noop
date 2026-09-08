# LNMP Troubleshooting & Disaster Recovery Guide — Version 3.0.0

This guide provides systematic diagnostic steps and solutions for common operational issues encountered when running LNMP v3.0.0 in production.

---

## 1. Fast Diagnostics & Health Checks

### Check Systemd Service Status
```bash
# Check status of API service and Monitoring Engine
sudo systemctl status netmon-api netmon-engine

# Verify auto-start on boot is enabled
sudo systemctl is-enabled netmon-api netmon-engine
```

### Inspect Application Logs
```bash
# Live stream API server logs
sudo journalctl -u netmon-api -f

# Live stream Monitoring Engine ICMP polling logs
sudo journalctl -u netmon-engine -f

# View platform error log file directly
tail -n 100 -f /var/log/netmon/error.log
```

---

## 2. Common Issues & Solutions

### A. ICMP Polling Fails with "Operation Not Permitted" / Raw Socket Permission Denied
* **Cause**: The `netmon-engine` daemon requires raw socket capability (`CAP_NET_RAW`) to craft ICMP packets without running as `root`.
* **Fix**:
  ```bash
  # Ensure traceroute and python have raw network capabilities
  sudo setcap cap_net_raw+ep $(command -v traceroute)
  
  # Restart monitoring engine
  sudo systemctl restart netmon-engine
  ```

### B. User Account Temporarily Locked Out (HTTP 403)
* **Cause**: 5 consecutive failed login attempts from a single IP within a 15-minute window trigger an IP-scoped security lockout.
* **Fix**:
  - Wait 15 minutes for the automated sliding lockout window to expire.
  - Or reset the user's password directly from the server CLI:
    ```bash
    sudo /opt/netmon/noop/deploy/reset-admin-password.sh <username> <new_password>
    ```

### C. Forgot Admin Password / Out-of-Band Recovery
* **Fix**:
  ```bash
  cd /opt/netmon/noop/deploy
  sudo ./reset-admin-password.sh <username> <new_password>
  ```

### D. TimescaleDB Chunk Compression Verification
* **Check Compression Status**:
  ```bash
  sudo -u postgres psql -d netmon -c "
    SELECT hypertable_name, total_chunks, number_compressed_chunks 
    FROM timescaledb_information.hypertable_compression_stats;
  "
  ```
* **Manually Trigger Compression on Older Chunks**:
  ```bash
  sudo -u postgres psql -d netmon -c "
    SELECT compress_chunk(c) 
    FROM show_chunks('endpoint_events', older_than => INTERVAL '7 days') c;
  "
  ```

### E. Frontend Shows "Unable to connect to LNMP Server" (HTTP 502 / Connection Refused)
* **Diagnosis**:
  1. Check if the Uvicorn FastAPI daemon is running locally:
     ```bash
     curl -I http://127.0.0.1:8000/api/v1/health
     ```
  2. Check Nginx reverse proxy configuration and error logs:
     ```bash
     sudo nginx -t
     sudo tail -n 50 /var/log/nginx/error.log
     ```
  3. Restart API service and Nginx:
     ```bash
     sudo systemctl restart netmon-api nginx
     ```

### F. Diagnostic Traceroutes Failing or Taking Too Long
* **Cause**: The target network or endpoint is dropping UDP/ICMP probe packets, or local firewall blocks outbound traceroutes.
* **Diagnosis**:
  ```bash
  # Test traceroute manually from server CLI
  traceroute -n -w 2 -m 15 <target_ip>
  ```
* **Note**: In LNMP v3.0.0, traceroute timeouts are handled gracefully and anonymous hops (`* * *`) are rendered safely without crashing topology calculations.

### G. Endpoint Telemetry, RTT Trends, or Transition Logs Appear Blank
* **Symptoms**:
  - Dashboard endpoint cards display live operational status and latency.
  - Clicking into **Endpoint Detail View** shows:
    - Blank state transition logs (*"No state transitions recorded in this period"*).
    - Blank RTT latency trend chart (*"No RTT data available for this period"*).
    - Missing state timeline history.
* **Cause**:
  - **Host Timezone Misconfiguration or Clock Skew**: The server's timezone or system clock is out of sync with the operational region or client browser. Because telemetry queries query events within strict time boundaries (`start_time <= end_dt`), a server clock lagging behind real time or configured with an incorrect timezone offset causes newly recorded events to fall outside the query window.
* **Fix**:
  1. Inspect the server's current time, timezone, and NTP synchronization:
     ```bash
     timedatectl status
     ```
  2. Set the correct regional timezone (e.g., `Europe/London`, `America/New_York`, `UTC`, `Africa/Lagos`):
     ```bash
     sudo timedatectl set-timezone <Your/Region_Timezone>
     ```
  3. Ensure Network Time Protocol (NTP) synchronization is enabled:
     ```bash
     sudo timedatectl set-ntp on
     ```
  4. Confirm that the system clock is synchronized:
     ```bash
     timedatectl
     ```
  5. Restart the monitoring daemons so queries and event logging immediately align with the synchronized clock:
     ```bash
     sudo systemctl restart netmon-engine netmon-api
     ```

---

## 3. Database Disaster Recovery

### Creating an Immediate Manual Backup
```bash
mkdir -p /var/backups/netmon
sudo PGPASSWORD="netmon_secure_password" pg_dump -h 127.0.0.1 -U netmon_user -d netmon -F p -f /var/backups/netmon/manual_backup_$(date +%Y%m%d_%H%M%S).sql
```

### Restoring from a Backup File
```bash
# 1. Stop platform daemons
sudo systemctl stop netmon-api netmon-engine

# 2. Restore database from SQL dump
sudo PGPASSWORD="netmon_secure_password" psql -h 127.0.0.1 -U netmon_user -d netmon -f /var/backups/netmon/<backup_file_name>.sql

# 3. Run latest schema migrations
cd /opt/netmon/noop/backend
sudo /opt/netmon/venv/bin/alembic upgrade head

# 4. Restart services
sudo systemctl start netmon-api netmon-engine
```
