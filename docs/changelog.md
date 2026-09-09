# LNMP Changelog & Evolutionary Architecture

All notable technical changes, architectural upgrades, security enhancements, and operational milestones for the Lightweight Network Monitoring Platform (LNMP) are documented in this file.

The versioning format follows [Semantic Versioning](https://semver.org/).

---

## [Version 3.1.0] — Enterprise Alerting & Notifications Engine
### 🔔 Multi-Channel Notifications, Outbound Security & Reporting Customization

| Upgrade Domain | Technical Implementation | Operational & Security Benefit |
| :--- | :--- | :--- |
| **Multi-Channel Alert Dispatcher** | Asynchronous background worker pool decoupled from the 32-second ICMP probe sweep budget via `asyncio.Queue` running entirely within `netmon-api`. | Guarantees zero latency jitter or sweep delay on high-frequency ICMP/TCP polling loops while delivering near real-time incident notifications. |
| **Universal Polyglot Webhooks** | Native support for Microsoft Teams Adaptive Cards v1.4, Teams HTML fallback ("Post as User" for bot-restricted tenants), Discord Rich Embeds, Slack Block Kit, and direct SMTP TLS. | Integrates effortlessly with corporate and developer chat platforms without external bridging proxies or third-party middleware. |
| **Hardened Outbound Security** | AES-256-GCM encryption at rest with HKDF-SHA256 key derivation for webhook URLs and SMTP credentials; socket-level DNS/IP validation blocking loopback and link-local metadata; CRLF header injection sanitization. | Eliminates secret exfiltration from database dumps, completely prevents Server-Side Request Forgery (SSRF) against internal resources, and secures email headers. |
| **Intelligent Alert Suppression** | Root-cause grouping suppressing individual children alerts during upstream DAG gateway outages; sliding-window flapping detection (max 1 alert per 5 min per endpoint/severity). | Eliminates alert fatigue, prevents notification spam during route flaps, and focuses operator attention on root causes. |
| **Hardware Master Toggle** | Master `alerting_enabled` boolean in system settings and database `app_settings` allowing instant suspension of all outbound notification traffic. | Allows low-spec edge or maintenance deployments to completely disable alerting workloads on demand with zero downtime. |
| **Spacious 4-Tab Administration Console** | Redesigned `SettingsView.vue` into 4 dedicated tabs (`🔔 Alert Channels`, `⚡ Performance & Storage`, `🛡️ Security & Discovery`, `👥 User Governance`), featuring an 800px modal and live diagnostic test probe button. | Streamlines system configuration, provides instant visual test validation before saving, and cleans up administrative workflows. |
| **Interactive CSV Column Customizer** | Redesigned 820px export configuration modal in `ReportsView.vue` with locked device identity columns (`Hostname`, `IP_Address`), toggleable metrics, Select All, and Reset actions. | Provides tailored, audit-compliant reporting outputs while guaranteeing immutable endpoint identity columns in every generated export. |

---

## [Version 3.0.7s]
### 🛡️ Production Security Hardening & Resilience Upgrades

| Upgrade Domain | Technical Implementation | Operational & Security Benefit |
| :--- | :--- | :--- |
| **Strict Session Wipe & Multi-Worker Governance** | Enforced strict `jti` validation (`if not jti: return False`), awaited session registration in login, awaited invalidation on logout/password reset, and directly queried persistent session store drivers in `get_current_user`. | Completely eliminates the multi-worker auth bypass under Uvicorn (`--workers 2`), preventing unauthorized session reuse and ensuring 100% session quota enforcement from second zero. |
| **Inter-Process Telemetry Relay & Split-Brain Remediation** | Integrated `telemetry_relay.py` in `netmon-api` to subscribe to `STATE_TRANSITION` and `NODE_STATE_CHANGE` via the active `EventBroker`, broadcasting to browser SSE and mutating the API's local in-memory `topology_manager` in $O(1)$ time. | Resolves the inter-process split-brain where `netmon-engine` and `netmon-api` operated in isolated memory spaces, restoring real-time web telemetry and live topology map updates. |
| **Synthetic SSL Probe Binary DER Parsing** | Added binary DER certificate decoding via `cryptography.x509.load_der_x509_certificate(bin_cert).not_valid_after_utc` when Python's `ssl` module returns an empty dictionary under `ssl.CERT_NONE`. | Prevents unhandled `TypeError` crashes during SSL probes against self-signed, internal, or untrusted host certificates. |
| **Storage Driver Precedence & Robust Asyncpg Event Broker** | Prioritized database `app_settings.performance_mode` over config defaults, added socket cleanup (`await self._redis_client.aclose()`), parameterized SQL notify queries (`SELECT pg_notify(:channel, :payload)`), and implemented dedicated unpooled `asyncpg` notification listener with exponential backoff. | Eliminates SQL injection vectors in notify publishing and prevents silent connection drops and split-brain broker fallbacks during Redis or PostgreSQL restarts. |
| **Uptime SLA Denominator & Keyset Telemetry Export** | Tailored `unknown_seconds` to the intersection of engine service gaps and the endpoint's actual active lifespan `[max(start_time, created_at), now_utc]`; added bulk `GET /api/v1/reports/fleet-summary`; refactored CSV telemetry export to deterministic keyset pagination on `(start_time, id)`. | Eliminates false 100% SLA ratings for newly onboarded endpoints, replaces $O(N)$ HTTP client request fan-outs with a single query, and eliminates quadratic table scan overhead during multi-month telemetry exports. |
| **Dynamic System Settings REST API & CIDR Netmask Hardening** | Implemented `GET` and `PATCH /api/v1/settings` backed by PostgreSQL `app_settings` table with automatic driver re-initialization; hardened `is_local_subnet_destination` to compute CIDRs using actual interface netmasks (`f"{addr.address}/{addr.netmask}"`) instead of hardcoded `/24`. | Replaces placebo browser `localStorage` settings with persistent backend configuration and fixes Layer-2 subnet auto-bypass on `/16`, `/23`, and `/8` subnets. |
| **Production Deployment Hardening & Fail-Safe Upgrade Pipeline** | Added `After=redis-server.service` and `Wants=redis-server.service` to systemd units; configured `proxy_buffering off;` and `proxy_read_timeout 86400s;` in Nginx template; restructured `deploy/upgrade.sh` to compile frontend assets before stopping daemons, support air-gapped pre-built `dist`, and halt safely on Alembic migration errors without `|| true`. | Eliminates boot-time race conditions between systemd units, prevents Nginx reverse-proxy SSE buffering, and prevents unrecoverable service downtime during live upgrades. |

### 🚀 Major Architectural Upgrades - [Version 3.0.0]

| Upgrade Domain | Technical Implementation | Operational & Performance Benefit |
| :--- | :--- | :--- |
| **SQLAlchemy 2.0 ORM & Repository Layer** | Migrated all database operations from raw SQL string sprawl to pure typed async declarative models (`backend/app/models/`) and a clean Repository Layer (`backend/app/repositories/`). | Eliminates SQL injection vectors, god controllers, and coupling; standardizes database access with full IDE autocompletion and type-safety. |
| **SQL-Level Pagination** | Implemented `limit` and `offset` query parameters across repositories with metadata envelopes (`total_count`, `page`, `page_size`, `total_pages`). | Drastically reduces server memory consumption and DB serialization overhead when querying large endpoint and event lists. |
| **Pydantic-Settings Centralization** | Modernized configuration management with nested `Settings` models reading from `/etc/netmon/config.toml` and environment variables. | Clean validation of system configurations on startup with clear error messages for missing or invalid parameters. |
| **60s Cycle Timing Budget Refactor** | Re-tuned monitoring cycle from `10 pings @ 6.0s` to `5 pings @ 8.0s` with randomized startup jitter (0–2000ms offset). | Guarantees probe pass completion in ~32s, leaving a spacious **28-second headroom window** before the minute boundary to eliminate thundering herds and DB lock contention. |
| **Dynamic In-Memory Endpoint Registry** | Thread-safe, asyncio concurrent `EndpointRegistry` with sub-minute lifecycle synchronization (`add_endpoint`, `update_endpoint`, `remove_endpoint`). | Enables zero-downtime endpoint onboarding and configuration updates without requiring engine daemon restarts. |
| **High-Fidelity Route Diagnostics** | Upgraded traceroute parameters to `traceroute -n -q 2 -w 3 -m 30 -I` with robust multi-probe latency extraction and automatic Layer-2 subnet bypass. | Eliminates silent hop parsing dropouts, measures multi-probe transit variability, and avoids wasteful traceroutes on direct broadcast segments. |
| **Dual-Driver Storage Architecture** | Abstracted `SessionStore` (`PostgresSessionStore`, `RedisSessionStore`) and `EventBroker` (`PostgresEventBroker`, `RedisEventBroker`) managed via `StorageDriverManager`. | Enables high-performance Redis in-memory acceleration while retaining 100% functionality on standalone PostgreSQL deployments. |
| **Async Argon2id Password Hashing** | Wrapped CPU-intensive password hashing and verification in `asyncio.to_thread` with trusted CIDR IP sanitization. | Prevents event-loop stalls under concurrent authentication traffic and guarantees accurate audit logging behind reverse proxies. |
| **Real-Time Server-Sent Events (SSE)** | High-throughput streaming endpoint `GET /api/v1/events/stream` emitting `STATE_TRANSITION`, `NODE_STATE_CHANGE`, and `RCA_INCIDENT` envelopes with 15s heartbeat pings. | Eliminates periodic client polling, reducing backend HTTP request load while providing instantaneous sub-second UI updates. |
| **Multi-Protocol Synthetic Probes** | Lightweight async probes for TCP port reachability, HTTP/HTTPS status validation, and SSL/TLS certificate expiry with strict SSRF defense. | Extends platform monitoring beyond ICMP to application-layer service health and certificate expiration alerts. |
| **Frozen-Physics Topology Recolor** | Real-time Vis-Network node recoloring upon SSE `NODE_STATE_CHANGE` events with locked physics (`physics: { enabled: false }`). | Updates network status colors in real time without causing node jitter, layout recalculations, or canvas movement. |
| **Dashboard Layout Overhaul** | Added Global Network Health KPI strip with live filter pills, dual view switcher (Visual Card Grid vs Dense Table), and real-time SSE connection badge. | Gives operators instant fleet-wide SLA visibility and high-density sorting capabilities across thousands of monitored devices. |
| **Admin Settings Console** | Dedicated administrative interface (`/settings`) for storage driver switching, L2 auto-bypass toggles, security timeouts, and user governance. | Simplifies runtime system tuning and user administration into a centralized web UI. |
| **Design System & Accessibility Polish** | High-contrast monochrome theme, tabular monospace numbers (`font-variant-numeric: tabular-nums`), WCAG 2.1 AA focus rings, and `aria-live` screen reader regions. | Guarantees compliance with accessibility standards and ensures maximum legibility in mission-critical NOC environments. |

---

## [Version 2.0 (Beta)]

### ✨ Feature Updates

| Feature Module | Technical Mechanism | Operational Benefit |
| :--- | :--- | :--- |
| **Crossing-Free Topology Map** | BFS DAG Longest-Path Layering (`Level(v) = max(Level(u) + 1)`) + Sugiyama (1981) Barycenter Reduction | Assigns exact physical hop depth tiers to every node; consolidates shared routes and completely eliminates false diagonal wire crossings. |
| **Gansner Coordinate Alignment** | Gansner / DOT (1993) heuristic (`blockShifting: true`, `parentCentralization: true`) | Centers parent routers directly above child clusters and provides spatial corridor shifting between distinct subtrees to avoid branch overlap. |
| **Horizontal ⇄ Vertical Switcher** | Dynamic `layout.hierarchical.direction` (`LR` vs `UD`) toggle with directional tangent constraints | Allows operators to switch between top-to-bottom and widescreen left-to-right layouts with animated, smooth transitions. |
| **Native Browser Password Autofill** | Standard HTML `name`, `autocomplete`, and unnested native input architecture | Enables instant 1-click autofill and credential saving across Chrome, Edge, Safari, Firefox, and password managers (Bitwarden, 1Password). |
| **Sliding 2-Hour Inactivity Timeout** | Sliding window token and session cookie renewal on active HTTP requests | Prevents unexpected mid-task logouts for active operators while guaranteeing that idle sessions safely expire after 120 minutes. |
| **Token-Based Session Quotas** | JWT `jti` tracking with in-memory FIFO rotation (Max 2 concurrent sessions) | Prevents account sharing and stale logins while allowing seamless multi-device use without conflicting with colleagues behind shared NAT/VPN gateways. |
| **IP-Scoped Lockout Protection** | Failed login attempt tracker keyed by `f"{client_ip}:{username}"` | External bot scans or single-device typos only lock out their specific origin IP, leaving legitimate admins at other locations unaffected. |
| **TimescaleDB 7-Day Compression** | Columnar hypertable chunk compression via migration `0005_v2_0_timescale_stability.py` | Reduces database storage growth by 90%+ while keeping years of historical telemetry 100% queryable for charts and reports. |
| **Continuous Aggregate Policies** | Automated hourly background refresh with crash-recovery catch-up | Accelerates historical baseline queries, ensures continuous aggregation, and saves server RAM during live dashboard usage. |

---

## [Version 1.5 (Beta)]

### ✨ Feature Updates

| Feature Module | Technical Mechanism | Operational Benefit |
| :--- | :--- | :--- |
| **Adaptive Statistical Baselines** | TimescaleDB continuous aggregates across 168 weekly hourly bins (7 days × 24 hours) | Automatically captures diurnal and weekend network traffic variations without manual threshold configuration. |
| **1D In-Memory Z-Score Baseline Cache** | Compact $O(1)$ RAM cache calculating dynamic bounds (`Z = (x - μ) / σ > 3.0`) | Eliminates static alert fatigue by triggering alarms only when latency statistically deviates from normal time-of-day baselines. |
| **Concurrent Background Diagnostics** | Non-blocking `asyncio.Semaphore(5)` queue triggered on first sub-cycle packet drop | Captures microsecond-level transit path snapshots before dynamic routing protocols (OSPF, BGP) can reconverge. |
| **Differential Root Cause Analysis (RCA)** | Automated side-by-side comparison of live failure traces against baseline snapshots | Instantly isolates whether an outage is caused by a local broadcast drop or an upstream carrier/transit link failure. |
| **In-Memory Directed Acyclic Graph (DAG)** | Sequential discovery pipeline with single-vertex Trie/Tree deduplication and orphan pruning | Builds an exact parent-child network topology map with zero duplicate transit nodes. |
| **Topological Alert Suppression** | Downstream dependency tracking marking children as `INFERRED_DOWN` | Silences cascading alert storms when an upstream aggregation router fails, highlighting the true root cause. |
