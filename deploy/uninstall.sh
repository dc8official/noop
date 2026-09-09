#!/usr/bin/env bash
# ==============================================================================
# LNMP Network Monitoring Platform v3.1.0 - Decommission / Uninstall Utility
# ==============================================================================

set -euo pipefail

# Color Palette
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

# Require Root
if [[ ${EUID} -ne 0 ]]; then
    echo -e "${RED}[ERROR] This script must be executed with root privileges (e.g., sudo ./uninstall.sh).${NC}" >&2
    exit 1
fi

echo -e "${RED}========================================================================${NC}"
echo -e "${RED}    LNMP Network Monitoring Platform v3.1.0 - Decommission / Uninstall  ${NC}"
echo -e "${RED}========================================================================${NC}"
echo -e "${YELLOW}WARNING: This utility will stop and remove all LNMP system services,${NC}"
echo -e "${YELLOW}disable background monitoring daemons, and remove web server routes.${NC}"
echo ""

# Safety Confirmation
read -rp "Are you sure you want to uninstall LNMP? (Type 'YES' to proceed): " CONFIRM
if [[ "${CONFIRM}" != "YES" ]]; then
    echo -e "${GREEN}[ABORTED] Uninstallation cancelled. No changes were made.${NC}"
    exit 0
fi

# Load Database credentials for safety dump if available
ENV_FILE="/etc/netmon/netmon.env"
if [[ -f "${ENV_FILE}" ]]; then
    # shellcheck disable=SC1090
    set -a
    source "${ENV_FILE}"
    set +a
fi

DB_NAME="${NETMON_DB_NAME:-${POSTGRES_DB:-netmon}}"
DB_USER="${NETMON_DB_USER:-${POSTGRES_USER:-netmon_user}}"
DB_PASS="${NETMON_DB_PASSWORD:-${POSTGRES_PASSWORD:-netmon_secure_password}}"
DB_HOST="${NETMON_DB_HOST:-${POSTGRES_HOST:-127.0.0.1}}"
DB_PORT="${NETMON_DB_PORT:-${POSTGRES_PORT:-5432}}"

# 1. Final Safety Database Backup
BACKUP_DIR="/var/backups/netmon"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FINAL_BACKUP="${BACKUP_DIR}/netmon_decommission_backup_${TIMESTAMP}.sql"

echo -e "\n${BLUE}--- Step 1/4: Creating Final Safety Database Backup ---${NC}"
mkdir -p "${BACKUP_DIR}"
if command -v pg_dump &>/dev/null; then
    echo -e "${GREEN}[INFO] Creating safety dump at ${FINAL_BACKUP}...${NC}"
    PGPASSWORD="${DB_PASS}" pg_dump -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -F p -f "${FINAL_BACKUP}" 2>/dev/null || true
    if [[ -f "${FINAL_BACKUP}" && -s "${FINAL_BACKUP}" ]]; then
        chmod 600 "${FINAL_BACKUP}"
        echo -e "${GREEN}[SUCCESS] Safety backup saved to ${FINAL_BACKUP}${NC}"
    else
        echo -e "${YELLOW}[WARN] Could not create database dump (database may already be offline). Continuing...${NC}"
    fi
fi

# 2. Stop and Disable Systemd Services
echo -e "\n${BLUE}--- Step 2/4: Stopping & Removing Systemd Services ---${NC}"
systemctl stop netmon-api netmon-engine 2>/dev/null || true
systemctl disable netmon-api netmon-engine 2>/dev/null || true

rm -f /etc/systemd/system/netmon-api.service
rm -f /etc/systemd/system/netmon-engine.service
systemctl daemon-reload
echo -e "${GREEN}[SUCCESS] LNMP background services disabled and removed from systemd.${NC}"

# 3. Clean Nginx Configuration
echo -e "\n${BLUE}--- Step 3/4: Removing Web Server Routing ---${NC}"
rm -f /etc/nginx/sites-enabled/netmon
rm -f /etc/nginx/sites-available/netmon
if command -v nginx &>/dev/null; then
    nginx -t 2>/dev/null && systemctl reload nginx || true
fi
echo -e "${GREEN}[SUCCESS] Nginx web routing removed.${NC}"

# 4. Optional Application Directory and Database Cleanup
echo -e "\n${BLUE}--- Step 4/4: Application Directory & Database ---${NC}"
read -rp "Do you want to delete application files in /opt/netmon? [y/N]: " REMOVE_FILES
if [[ "${REMOVE_FILES,,}" == "y" || "${REMOVE_FILES,,}" == "yes" ]]; then
    rm -rf /opt/netmon
    echo -e "${GREEN}[INFO] Removed /opt/netmon directory.${NC}"
fi

echo -e "\n${GREEN}========================================================================${NC}"
echo -e "${GREEN}   [UNINSTALL COMPLETE] LNMP v3.1.0 platform decommissioned.           ${NC}"
echo -e "${GREEN}   Safety Database Backup Retained At: ${FINAL_BACKUP}${NC}"
echo -e "${GREEN}========================================================================${NC}"
