# LNMP: Network Monitoring Platform v3.0.0

A high-precision, decoupled network telemetry and monitoring solution designed for continuous endpoint status verification, low-latency multi-protocol polling, adaptive statistical alerting, automated root-cause analysis (RCA), real-time Server-Sent Events (SSE), dual-driver storage acceleration, and dynamic topology visualization with crossing-free layout routing.

---

## Architectural Overview

The platform is decoupled into independent, modular layers to guarantee continuous telemetry collection regardless of client-side dashboard activity, heavy API load, or temporary network disruptions:

* **SQLAlchemy 2.0 ORM & Repository Pattern:** Clean data access layer separating business logic from database operations, eliminating raw SQL queries and implementing SQL-level pagination (`limit`, `offset`) across all entities.
* **5-Ping @ 8.0s Concurrency Sweeper:** Polling engine tuned with a spacious **28-second headroom window** before the minute boundary and 0–2000ms randomized startup jitter, completely eliminating connection contention and thundering herds.
* **Dynamic In-Memory Endpoint Registry:** Concurrent-safe registry supporting zero-downtime, sub-minute dynamic additions, updates, and deletions of monitored targets without service restarts.
* **High-Fidelity Route Diagnostics:** Upgraded traceroute engine (`traceroute -n -q 2 -w 3 -m 30 -I`) with multi-probe latency parsing, raw ICMP capability isolation (`CAP_NET_RAW`), and Layer-2 subnet auto-bypass.
* **Real-Time Server-Sent Events (SSE) Stream:** Asynchronous event broker streaming telemetry envelopes (`STATE_TRANSITION`, `NODE_STATE_CHANGE`, `RCA_INCIDENT`) and 15-second heartbeat keep-alives via `GET /api/v1/events/stream`.
* **Multi-Protocol Synthetic Probes:** Lightweight async probes verifying TCP port reachability, HTTP/HTTPS status code validation, and SSL/TLS certificate expiry with strict SSRF defense.
* **Dual-Driver Storage Architecture:** Seamlessly switches between **PostgreSQL-Native** (`LISTEN/NOTIFY` + table sessions) and **Redis-Accelerated** (Pub/Sub + in-memory sessions) drivers via configuration and admin settings.
* **Interactive Crossing-Free Topology Map:** Vue 3 Vis-Network visualizer implementing **BFS DAG Longest-Path Layering** (`Level(v) = max(Level(u) + 1)`), **Sugiyama (1981)** barycenter crossing reduction, **Gansner (1993)** coordinate alignment, **frozen-physics real-time recoloring**, and **Horizontal (LR) ⇄ Vertical (UD)** layout switching.
* **Enterprise Frontend & Accessibility Overhaul:** High-contrast monochrome design system, top summary KPI ribbon with instant filter pills, **Dual View Switcher** (Visual Card Grid vs. Dense Sortable Table), tabular monospace numbers, and WCAG 2.1 AA keyboard focus indicators.
* **TimescaleDB Compression & Retention:** 7-day chunk compression (90%+ disk savings), automated continuous aggregates, and daily automated 90-day retention cleanup.
* **Security & Session Governance:** Sliding 2-hour inactivity timeouts, token-based concurrent session quotas (max 2 active sessions with FIFO rotation), and IP-scoped failed login lockouts (`<Client_IP>:<Username>`).

---

## Detailed Documentation Suite

For comprehensive guides, references, and operational procedures, refer to the `docs/` directory:

* **[Changelog & Technical Evolution](docs/changelog.md):** Complete release notes and evolutionary milestones from Version 1.0 to Version 3.0.0.
* **[Architecture Deep-Dive](docs/architecture.md):** In-depth analysis of the Repository Layer, Dual-Driver Storage, Concurrency Sweeper, and Topology DAG.
* **[Deployment & Operations Guide](docs/deployment.md):** Production installation, automated in-place upgrades (`upgrade.sh`), Redis configuration, and health verification.
* **[Disaster Recovery & Restoration Runbook](deploy/RESTORE.md):** Step-by-step procedures for restoring TimescaleDB backups, running Alembic migrations, and flushing Redis cache.
* **[User & Operator Guide](docs/user-guide.md):** Guide to navigating the Live KPI ribbon, Card/Table view switcher, High-Fidelity traceroutes, and Admin Settings.
* **[API Reference](docs/api-reference.md):** Complete documentation for REST endpoints, SSE streams (`/events/stream`), pagination parameters, and synthetic probe schemas.
* **[Database & TimescaleDB Deep-Dive](docs/database.md):** Full schema dictionary, hypertable partitioning, 7-day chunk compression, and continuous aggregate policies.
* **[Security Model & Threat Hardening](docs/security.md):** Authentication matrix, Argon2id password hashing, sliding sessions, lockout defense, and Linux capability isolation.
* **[SLA Calculation Methodology](docs/sla-calculation.md):** Mathematical formulation of uptime availability, flap suppression, and blackout neutralization.
* **[Troubleshooting Runbook](docs/troubleshooting.md):** Step-by-step diagnostic workflows, permission fixes, and log inspection.
* **[Developer Guide](docs/developer-guide.md):** Local setup instructions for Vite and Uvicorn, plus guidelines for contributing via Alembic migrations.

---

## Technical Stack

* **Backend:** Python 3.10+, FastAPI, SQLAlchemy 2.0 (Async Declarative Models & Repository Layer), Pydantic Settings, Alembic, Native `asyncio`, Argon2id
* **Storage & Caching:** PostgreSQL 14+ with TimescaleDB Extension, Redis 6+ (Pub/Sub & Session Cache Acceleration)
* **Frontend:** Vue 3 (Composition API), Vite, PrimeVue (Aura Theme Preset), Chart.js, `vis-network` (BFS + Sugiyama Crossing Reduction)
* **System Layer:** Linux `systemd` (Auto-Start Enabled), Native Raw Sockets (`CAP_NET_RAW` capability), System `traceroute`
* **Logging:** Python `RotatingFileHandler` (~150MB bounded footprint) + `systemd-journald`

---

## Recommended System Specifications

### Hardware Sizing Matrix

| Deployment Scale | Monitored Endpoints | CPU Cores | Memory (RAM) | Storage (SSD) | Recommended Use Case |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Small / Edge** | Up to 100 | 1 vCPU | 2 GB RAM | 10 GB SSD | Home lab, edge monitoring, small office networks. |
| **Medium Enterprise** | 100 – 500 | 2 vCPUs | 4 GB RAM | 25 GB SSD | Branch networks, regional datacenter monitoring. |
| **Large Scale** | 500 – 2,000+ | 4+ vCPUs | 8 GB+ RAM | 50 GB+ NVMe | Multi-site enterprise datacenters & ISP backbones. |

---

## Getting Started (Production Deployment)

### Pre-Installation Requirement: System Timezone & NTP Time Synchronization

> [!IMPORTANT]
> **Timezone Alignment & Clock Synchronization**:
> LNMP telemetry analysis, uptime SLA calculation, and real-time state transition logging rely on precise timestamp filtering (`start_time <= end_dt`). If the server's timezone or system clock is out of sync with your operational region or client endpoints, newly captured telemetry events, RTT trends, and transition logs may appear blank or be excluded from query windows.
>
> Before installing or starting LNMP services, configure your host's regional timezone and enable network time synchronization (NTP):
>
> ```bash
> # Set the server timezone to your operational region (e.g. Europe/London, America/New_York, UTC, Africa/Lagos)
> sudo timedatectl set-timezone <Your/Region_Timezone>
>
> # Enable Network Time Protocol (NTP) synchronization
> sudo timedatectl set-ntp on
>
> # Verify time synchronization and active timezone
> timedatectl status
> ```

### 1. Fresh Installation

```bash
sudo -i
git clone https://github.com/dc8official/lnmp.git
cd lnmp/deploy
./install.sh
```

### 2. Upgrading to v3.0.0 (Zero Historical Data Loss)

To upgrade an existing installation to Version 3.0.0:

```bash
cd ~/lnmp
git pull origin main
sudo ./deploy/upgrade.sh
```

*(Alternatively, if running directly on the production host without a cloned repository, you can execute `sudo bash /opt/netmon/noop/deploy/upgrade.sh`)*

The upgrade utility automatically executes:
1. **Pre-Upgrade Backup**: Dumps a timestamped PostgreSQL SQL backup to `/var/backups/netmon/`.
2. **System Dependencies**: Installs and starts `redis-server` and sets `CAP_NET_RAW` capabilities on `traceroute`.
3. **Smart Config Migration**: Updates `/etc/netmon/config.toml` defaults (5 pings @ 8s, 120m timeout, Redis section) without overwriting secrets.
4. **Service Pause**: Gracefully pauses background daemons.
5. **Code & Dependency Sync**: Pulls latest updates, installs Python requirements, and compiles Vue 3 assets.
6. **Alembic Forward Migrations**: Runs `alembic upgrade head` while preserving all TimescaleDB hypertables and continuous aggregates.
7. **Systemd Unit Refresh & Restart**: Reloads daemons, enables auto-start, and restarts `redis-server`, `netmon-api`, `netmon-engine`, and `nginx`.
8. **Health Check**: Validates live API status and version endpoint (`/api/v1/version`).

---

## License & Authorship

Core Architecture designed and authored by **Kenneth Nnorom**.

Website: [kennethnnorom.com](https://kennethnnorom.com) | LinkedIn: [linkedin.com/in/kennethnnorom](https://www.google.com/search?q=https://linkedin.com/in/kennethnnorom)

This project is licensed under the terms of the **Apache License 2.0**. See the [LICENSE](LICENSE) file for complete details.
