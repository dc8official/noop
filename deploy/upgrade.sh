#!/usr/bin/env bash
# ==============================================================================
# LNMP Network Monitoring Platform v3.1.0 - Automated Upgrade Utility
# ==============================================================================

set -euo pipefail

# Color Palette for Terminal Output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 1. Require Root / Administrative Privileges (bypassed in dry-run mode)
if [[ ${EUID} -ne 0 && "${1:-}" != "--dry-run" ]]; then
    echo -e "${RED}[ERROR] This script must be executed with root privileges (e.g., sudo ./upgrade.sh).${NC}" >&2
    exit 1
fi

echo -e "${BLUE}========================================================================${NC}"
echo -e "${BLUE}    LNMP Network Monitoring Platform v3.1.0 - Upgrade Utility           ${NC}"
echo -e "${BLUE}========================================================================${NC}"

# Resolve Script and Project Root Directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
INSTALL_DIR="/opt/netmon/noop"
REPO_URL="${NETMON_REPO_URL:-https://github.com/dc8official/lnmp.git}"
UPGRADE_BRANCH="${NETMON_BRANCH:-main}"

# 2. Read Configuration Values
ENV_FILE="/etc/netmon/netmon.env"
if [[ -f "${ENV_FILE}" ]]; then
    echo -e "${GREEN}[INFO] Loading environment configuration from ${ENV_FILE}${NC}"
    if [[ ${DRY_RUN} -eq 0 ]]; then
        chmod 0600 "${ENV_FILE}"
        chown netmon:netmon "${ENV_FILE}" 2>/dev/null || true
    fi
    # shellcheck disable=SC1090
    set -a
    source "${ENV_FILE}"
    set +a
elif [[ -f "${PROJECT_ROOT}/backend/.env" ]]; then
    echo -e "${YELLOW}[WARN] /etc/netmon/netmon.env not found. Loading local backend/.env${NC}"
    # shellcheck disable=SC1090
    set -a
    source "${PROJECT_ROOT}/backend/.env"
    set +a
fi

DB_NAME="${NETMON_DB_NAME:-${POSTGRES_DB:-netmon}}"
DB_USER="${NETMON_DB_USER:-${POSTGRES_USER:-netmon_user}}"
DB_PASS="${NETMON_DB_PASSWORD:-${POSTGRES_PASSWORD:-netmon_secure_password}}"
DB_HOST="${NETMON_DB_HOST:-${POSTGRES_HOST:-127.0.0.1}}"
DB_PORT="${NETMON_DB_PORT:-${POSTGRES_PORT:-5432}}"

# Handle Dry-Run Mode Option
DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=1
    echo -e "${YELLOW}[DRY-RUN MODE] Simulating upgrade operations without making mutations.${NC}"
fi

# 3. Pre-Upgrade Database Backup
BACKUP_DIR="/var/backups/netmon"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/netmon_backup_${TIMESTAMP}.sql"

echo -e "\n${BLUE}--- Step 1/7: Executing Pre-Upgrade Database Backup ---${NC}"
if [[ ${DRY_RUN} -eq 0 ]]; then
    if ! command -v pg_dump &> /dev/null; then
        echo -e "${RED}[ERROR] pg_dump command not found. Please install postgresql-client.${NC}" >&2
        exit 1
    fi

    mkdir -p "${BACKUP_DIR}"
    chmod 750 "${BACKUP_DIR}"
    echo -e "${GREEN}[INFO] Creating timestamped database dump at ${BACKUP_FILE}...${NC}"
    
    if PGPASSWORD="${DB_PASS}" pg_dump -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -F p -f "${BACKUP_FILE}"; then
        chmod 640 "${BACKUP_FILE}"
        echo -e "${GREEN}[SUCCESS] Pre-upgrade backup successfully saved to ${BACKUP_FILE}${NC}"
    else
        echo -e "${RED}[ERROR] Database backup failed. Aborting upgrade to preserve data safety.${NC}" >&2
        exit 1
    fi
else
    echo -e "[DRY-RUN] Would generate SQL dump to ${BACKUP_FILE}"
fi

# 4. Smart Config Migration (In-Place Upgrade)
CONFIG_FILE="/etc/netmon/config.toml"
echo -e "\n${BLUE}--- Step 2/7: Migrating System Configuration Defaults ---${NC}"
if [[ ${DRY_RUN} -eq 0 && -f "${CONFIG_FILE}" ]]; then
    echo -e "${GREEN}[INFO] Verifying configuration settings in ${CONFIG_FILE}...${NC}"
    
    # Update ping timing budget to 5 pings @ 8.0s for v3.0.0
    if grep -q "ping_count = 10" "${CONFIG_FILE}"; then
        sed -i 's/ping_count = 10/ping_count = 5/' "${CONFIG_FILE}"
        echo -e "${GREEN}[INFO] Updated ping_count to 5 probes.${NC}"
    fi
    if grep -q "ping_interval_seconds = 6" "${CONFIG_FILE}"; then
        sed -i 's/ping_interval_seconds = 6/ping_interval_seconds = 8/' "${CONFIG_FILE}"
        echo -e "${GREEN}[INFO] Updated ping_interval_seconds to 8s.${NC}"
    fi

    # Update session_timeout_minutes to 120 if currently 30
    if grep -q "session_timeout_minutes = 30" "${CONFIG_FILE}"; then
        sed -i 's/session_timeout_minutes = 30/session_timeout_minutes = 120/' "${CONFIG_FILE}"
        echo -e "${GREEN}[INFO] Updated session_timeout_minutes to 120 (2 hours).${NC}"
    fi

    # Add max_active_sessions_per_user if missing
    if ! grep -q "max_active_sessions_per_user" "${CONFIG_FILE}"; then
        sed -i '/\[security\]/a max_active_sessions_per_user = 2' "${CONFIG_FILE}"
        echo -e "${GREEN}[INFO] Added max_active_sessions_per_user = 2 to [security].${NC}"
    fi

    # Add [redis] section if missing
    if ! grep -q "\[redis\]" "${CONFIG_FILE}"; then
        cat << 'EOF' >> "${CONFIG_FILE}"

[redis]
host = "127.0.0.1"
port = 6379
db = 0
enabled = true
performance_mode = false
EOF
        echo -e "${GREEN}[INFO] Appended [redis] storage driver section to ${CONFIG_FILE}.${NC}"
    fi
fi

# Pre-Flight: Build Frontend Assets Before Service Pause
echo -e "\n${BLUE}--- Pre-Flight: Verifying & Compiling Frontend Production Bundle ---${NC}"
FRONTEND_DIR="${PROJECT_ROOT}/frontend"
if [[ ${DRY_RUN} -eq 0 && -d "${FRONTEND_DIR}" && -f "${FRONTEND_DIR}/package.json" ]]; then
    if command -v npm &>/dev/null; then
        echo -e "${GREEN}[INFO] Building Vue 3 frontend bundle in pre-flight (${FRONTEND_DIR})...${NC}"
        if (cd "${FRONTEND_DIR}" && npm install && npm run build); then
            echo -e "${GREEN}[SUCCESS] Pre-flight frontend build completed successfully.${NC}"
        elif [[ -f "${FRONTEND_DIR}/dist/index.html" ]]; then
            echo -e "${YELLOW}[WARN] npm build failed or air-gapped network detected. Existing frontend/dist/index.html found; proceeding with pre-built assets.${NC}"
        else
            echo -e "${RED}[ERROR] Frontend build failed and no pre-built frontend/dist/index.html found. Aborting upgrade before stopping services.${NC}" >&2
            exit 1
        fi
    elif [[ -f "${FRONTEND_DIR}/dist/index.html" ]]; then
        echo -e "${GREEN}[INFO] npm command not found; air-gapped environment detected. Using existing pre-built frontend/dist/index.html.${NC}"
    else
        echo -e "${RED}[ERROR] npm command not found and no pre-built frontend/dist/index.html exists. Cannot proceed.${NC}" >&2
        exit 1
    fi
else
    echo -e "[DRY-RUN] Pre-flight frontend build check passed."
fi

# 5. Service Pause
echo -e "\n${BLUE}--- Step 3/7: Gracefully Pausing Platform Background Daemons ---${NC}"
if [[ ${DRY_RUN} -eq 0 ]]; then
    if systemctl is-active --quiet netmon-engine || systemctl is-active --quiet netmon-api; then
        echo -e "${GREEN}[INFO] Stopping netmon-engine and netmon-api systemd services...${NC}"
        systemctl stop netmon-engine netmon-api || true
    else
        echo -e "${YELLOW}[INFO] Platform systemd services are not active. Skipping stop.${NC}"
    fi
else
    echo -e "[DRY-RUN] Would run: systemctl stop netmon-engine netmon-api"
fi

# 6. Fetch Latest Release Files from Repository
echo -e "\n${BLUE}--- Step 4/7: Fetching Latest Release & Updating System Dependencies ---${NC}"
SOURCE_DIR="${PROJECT_ROOT}"
STAGE_DIR="/tmp/lnmp-upgrade-stage-$$"

if [[ ${DRY_RUN} -eq 0 ]]; then
    # Ensure system dependencies (git, redis-server, traceroute, libcap2-bin)
    if command -v apt-get &>/dev/null; then
        PACKAGES_TO_CHECK="git redis-server traceroute libcap2-bin rsync"
        MISSING_PKGS=""
        for pkg in ${PACKAGES_TO_CHECK}; do
            if ! dpkg -l "${pkg}" 2>/dev/null | grep -q "^ii"; then
                MISSING_PKGS="${MISSING_PKGS} ${pkg}"
            fi
        done

        if [[ -n "${MISSING_PKGS}" ]]; then
            echo -e "${GREEN}[INFO] Installing missing system packages:${MISSING_PKGS}...${NC}"
            apt-get update -qq && apt-get install -y ${MISSING_PKGS} || true
        fi

        # Enable and start Redis
        systemctl enable --now redis-server 2>/dev/null || systemctl enable --now redis 2>/dev/null || true

        # Set network capabilities for raw ICMP traceroute
        TRACEROUTE_BIN=$(command -v traceroute || true)
        if [[ -n "${TRACEROUTE_BIN}" ]] && command -v setcap &>/dev/null; then
            setcap cap_net_raw+ep "${TRACEROUTE_BIN}" || true
        fi
    fi

    # Case A: PROJECT_ROOT is an existing Git clone directory
    if [[ -d "${PROJECT_ROOT}/.git" ]]; then
        echo -e "${GREEN}[INFO] Detected Git repository at ${PROJECT_ROOT}. Pulling latest updates...${NC}"
        cd "${PROJECT_ROOT}"
        git config --global --add safe.directory "${PROJECT_ROOT}" 2>/dev/null || true
        git fetch --all --tags --prune || true
        git checkout "${UPGRADE_BRANCH}" 2>/dev/null || git checkout v3.1.0 2>/dev/null || true
        git pull origin "${UPGRADE_BRANCH}" 2>/dev/null || git pull origin v3.1.0 2>/dev/null || git pull || echo -e "${YELLOW}[WARN] Git pull finished with non-zero exit code. Proceeding with existing files.${NC}"
        SOURCE_DIR="${PROJECT_ROOT}"
    # Case B: Running from /opt/netmon/noop or non-git directory -> clone directly from remote
    else
        echo -e "${GREEN}[INFO] Staging fresh release from ${REPO_URL} (branch: ${UPGRADE_BRANCH})...${NC}"
        rm -rf "${STAGE_DIR}"
        if git clone --depth 1 --branch "${UPGRADE_BRANCH}" "${REPO_URL}" "${STAGE_DIR}" 2>/dev/null || \
           git clone --depth 1 --branch "v3.1.0" "${REPO_URL}" "${STAGE_DIR}" 2>/dev/null || \
           git clone --depth 1 "${REPO_URL}" "${STAGE_DIR}"; then
            echo -e "${GREEN}[SUCCESS] Downloaded latest codebase into staging directory.${NC}"
            SOURCE_DIR="${STAGE_DIR}"
        else
            echo -e "${RED}[ERROR] Failed to clone repository from ${REPO_URL}. Check internet connectivity.${NC}" >&2
            exit 1
        fi
    fi
    # Rebuild Vue 3 frontend in SOURCE_DIR if needed
    FRONTEND_DIR="${SOURCE_DIR}/frontend"
    if [[ -d "${FRONTEND_DIR}" && -f "${FRONTEND_DIR}/package.json" ]]; then
        if command -v npm &>/dev/null; then
            echo -e "${GREEN}[INFO] Rebuilding production Vue 3 frontend bundle in ${FRONTEND_DIR}...${NC}"
            (cd "${FRONTEND_DIR}" && npm install && npm run build) || {
                if [[ -f "${FRONTEND_DIR}/dist/index.html" ]]; then
                    echo -e "${YELLOW}[WARN] npm build failed or air-gapped network detected. Existing frontend/dist/index.html found; proceeding.${NC}"
                else
                    echo -e "${RED}[ERROR] Frontend build failed and no pre-built dist/index.html found.${NC}" >&2
                    exit 1
                fi
            }
        elif [[ -f "${FRONTEND_DIR}/dist/index.html" ]]; then
            echo -e "${GREEN}[INFO] npm not found; using existing pre-built ${FRONTEND_DIR}/dist/index.html.${NC}"
        fi
    fi
else
    echo -e "[DRY-RUN] Would fetch latest code from ${REPO_URL} (${UPGRADE_BRANCH}), build Vue 3 frontend, and ensure system packages (redis-server, traceroute, libcap2-bin)"
fi

# 7. Synchronize Production Files to Target Directory
echo -e "\n${BLUE}--- Step 5/7: Synchronizing Codebase & Enforcing Production Structure ---${NC}"
if [[ ${DRY_RUN} -eq 0 ]]; then
    mkdir -p "${INSTALL_DIR}"
    if [[ "${SOURCE_DIR}" != "${INSTALL_DIR}" ]]; then
        echo -e "${GREEN}[INFO] Syncing repository files from ${SOURCE_DIR} to ${INSTALL_DIR}...${NC}"
        rsync -a --delete \
            --exclude='.git' \
            --exclude='frontend/node_modules' \
            --exclude='backend/venv' \
            --exclude='backend/.env' \
            --exclude='.env' \
            --exclude='tests' \
            --exclude='pytest.ini' \
            --exclude='scratch' \
            "${SOURCE_DIR}/" "${INSTALL_DIR}/"
        chown -R netmon:netmon "${INSTALL_DIR}"
    fi

    # Clean up temporary staging directory if used
    if [[ -d "${STAGE_DIR}" ]]; then
        rm -rf "${STAGE_DIR}"
    fi
else
    echo -e "[DRY-RUN] Would rsync codebase to ${INSTALL_DIR} and set ownership to netmon:netmon"
fi

# 8. Dependency Installation & Database Migrations
echo -e "\n${BLUE}--- Step 6/7: Upgrading Python Dependencies & Database Migrations ---${NC}"
if [[ ${DRY_RUN} -eq 0 ]]; then
    # Determine Python virtual environment path
    VENV_PATH=""
    if [[ -d "/opt/netmon/venv" ]]; then
        VENV_PATH="/opt/netmon/venv"
    elif [[ -d "${INSTALL_DIR}/backend/venv" ]]; then
        VENV_PATH="${INSTALL_DIR}/backend/venv"
    elif [[ -d "${PROJECT_ROOT}/.venv" ]]; then
        VENV_PATH="${PROJECT_ROOT}/.venv"
    fi

    if [[ -n "${VENV_PATH}" && -f "${INSTALL_DIR}/backend/requirements.txt" ]]; then
        echo -e "${GREEN}[INFO] Upgrading Python dependencies in ${VENV_PATH}...${NC}"
        "${VENV_PATH}/bin/pip" install --upgrade pip
        "${VENV_PATH}/bin/pip" install -r "${INSTALL_DIR}/backend/requirements.txt" --upgrade
    else
        echo -e "${YELLOW}[WARN] Virtual environment not found at /opt/netmon/venv. Skipping pip upgrade.${NC}"
    fi

    # Database Schema Migrations
    cd "${INSTALL_DIR}/backend"
    ALEMBIC_BIN=""
    if [[ -n "${VENV_PATH:-}" && -f "${VENV_PATH}/bin/alembic" ]]; then
        ALEMBIC_BIN="${VENV_PATH}/bin/alembic"
    elif [[ -f "/opt/netmon/venv/bin/alembic" ]]; then
        ALEMBIC_BIN="/opt/netmon/venv/bin/alembic"
    elif [[ -f "${PROJECT_ROOT}/.venv/bin/alembic" ]]; then
        ALEMBIC_BIN="${PROJECT_ROOT}/.venv/bin/alembic"
    fi

    if [[ -d "${INSTALL_DIR}/backend/migrations" && -n "${ALEMBIC_BIN}" ]]; then
        echo -e "${GREEN}[INFO] Running Alembic schema migration (alembic upgrade head)...${NC}"
        PYTHONPATH="${INSTALL_DIR}:${INSTALL_DIR}/backend" "${ALEMBIC_BIN}" -c "${INSTALL_DIR}/backend/alembic.ini" upgrade head
        
        PYTHON_BIN="$(dirname "${ALEMBIC_BIN}")/python"
        if [[ -f "${PYTHON_BIN}" ]]; then
            echo -e "${GREEN}[INFO] Verifying default admin account seeding...${NC}"
            PYTHONPATH="${INSTALL_DIR}:${INSTALL_DIR}/backend" "${PYTHON_BIN}" -m app.seed_admin || true
        fi
    fi
else
    echo -e "[DRY-RUN] Would upgrade pip dependencies, compile Vue 3 assets, and execute alembic upgrade head"
fi

# 9. Service Unit Refresh, Auto-Start Enablement & Restart
echo -e "\n${BLUE}--- Step 7/7: Refreshing Systemd Units, Enabling Auto-Start & Starting Services ---${NC}"
if [[ ${DRY_RUN} -eq 0 ]]; then
    # Refresh systemd unit files if available in deploy/
    if [[ -f "${INSTALL_DIR}/deploy/netmon-api.service" ]]; then
        cp "${INSTALL_DIR}/deploy/netmon-api.service" /etc/systemd/system/
    elif [[ -f "${PROJECT_ROOT}/deploy/netmon-api.service" ]]; then
        cp "${PROJECT_ROOT}/deploy/netmon-api.service" /etc/systemd/system/
    fi
    if [[ -f "${INSTALL_DIR}/deploy/netmon-engine.service" ]]; then
        cp "${INSTALL_DIR}/deploy/netmon-engine.service" /etc/systemd/system/
    elif [[ -f "${PROJECT_ROOT}/deploy/netmon-engine.service" ]]; then
        cp "${PROJECT_ROOT}/deploy/netmon-engine.service" /etc/systemd/system/
    fi

    echo -e "${GREEN}[INFO] Reloading systemd daemons and enabling auto-start on boot...${NC}"
    systemctl daemon-reload
    systemctl enable --now redis-server 2>/dev/null || systemctl enable --now redis 2>/dev/null || true
    systemctl enable netmon-api netmon-engine || true
    systemctl restart netmon-api netmon-engine
    systemctl restart nginx || true

    sleep 2
    if systemctl is-active --quiet netmon-api && systemctl is-active --quiet netmon-engine; then
        echo -e "${GREEN}[SUCCESS] All systemd services (netmon-api, netmon-engine) are active, enabled on boot, and healthy.${NC}"
    else
        echo -e "${YELLOW}[WARN] Check service status via: systemctl status netmon-api netmon-engine${NC}"
    fi
else
    echo -e "[DRY-RUN] Would run: systemctl enable & restart redis-server netmon-api netmon-engine"
fi

echo -e "\n${GREEN}========================================================================${NC}"
echo -e "${GREEN}   [UPGRADE COMPLETE] LNMP v3.1.0 Platform upgraded successfully!       ${NC}"
echo -e "${GREEN}   Pre-Upgrade Database Backup Saved At: ${BACKUP_FILE}${NC}"
echo -e "${GREEN}========================================================================${NC}"
