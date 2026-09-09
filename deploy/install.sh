#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# lnmp Network Monitoring Platform v3.1.0 - Production Installer
# Supports: Debian 12+, Ubuntu 22.04+
# Usage: sudo bash deploy/install.sh [--dry-run]
# ============================================================

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "DRY RUN MODE: No changes will be made."
fi

DB_PASS=""
SECRET_KEY=""
DOMAIN_NAME=""

# Self-locate project root from script location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Installation target directory
INSTALL_DIR="/opt/netmon/noop"
VENV_DIR="/opt/netmon/venv"
CONFIG_DIR="/etc/netmon"
LOG_DIR="/var/log/netmon"
BACKUP_DIR="/var/backups/netmon"
ENV_FILE="$CONFIG_DIR/netmon.env"
CONFIG_FILE="$CONFIG_DIR/config.toml"

# ============================================================
print_header() {
    echo ""
    echo "========================================================"
    echo "  $1"
    echo "========================================================"
}

run() {
    # Executes a command or prints it in dry-run mode
    local description="$1"
    shift
    if [ "$DRY_RUN" = true ]; then
        echo "[DRY RUN] $description"
        echo "          Command: $*"
    else
        echo "--> $description"
        "$@"
    fi
}

check_root() {
    if [ "$EUID" -ne 0 ] && [ "$DRY_RUN" = false ]; then
        echo "Error: This script must be run as root."
        echo "Usage: sudo bash deploy/install.sh"
        exit 1
    fi
}

# ============================================================
print_header "Step 1: Checking root privileges"
check_root

# ============================================================
print_header "Step 2: Installing prerequisite tools"

PREREQS="curl wget gnupg lsb-release ca-certificates apt-transport-https"
if [ "$DRY_RUN" = false ]; then
    apt-get update -qq
    apt-get install -y $PREREQS
else
    echo "[DRY RUN] Would install prerequisites: $PREREQS"
fi

# ============================================================
print_header "Step 3: Adding required APT repositories"

# NodeSource Node.js 20
if [ ! -f "/etc/apt/sources.list.d/nodesource.list" ]; then
    run "Adding NodeSource Node.js 20 repository" \
        bash -c "curl -fsSL https://deb.nodesource.com/setup_20.x | bash -"
else
    echo "NodeSource repository already configured."
fi

# PostgreSQL PGDG
if [ ! -f "/etc/apt/sources.list.d/pgdg.list" ]; then
    if [ "$DRY_RUN" = false ]; then
        echo "--> Adding PostgreSQL PGDG repository"
        curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
            | gpg --dearmor \
            -o /usr/share/keyrings/postgresql-keyring.gpg
        echo "deb [signed-by=/usr/share/keyrings/postgresql-keyring.gpg] \
https://apt.postgresql.org/pub/repos/apt \
$(lsb_release -cs)-pgdg main" \
            | tee /etc/apt/sources.list.d/pgdg.list
    else
        echo "[DRY RUN] Would add PostgreSQL PGDG repository"
    fi
else
    echo "PostgreSQL PGDG repository already configured."
fi

# TimescaleDB
if [ ! -f "/etc/apt/sources.list.d/timescaledb.list" ]; then
    if [ "$DRY_RUN" = false ]; then
        echo "--> Adding TimescaleDB repository"
        wget -qO - \
            https://packagecloud.io/timescale/timescaledb/gpgkey \
            | gpg --dearmor \
            -o /usr/share/keyrings/timescaledb-keyring.gpg

        OS_ID=$(lsb_release -is | tr '[:upper:]' '[:lower:]')
        OS_CODENAME=$(lsb_release -cs)

        if [ "$OS_ID" = "debian" ]; then
            REPO_PATH="debian"
        else
            REPO_PATH="ubuntu"
        fi

        echo "deb [signed-by=/usr/share/keyrings/timescaledb-keyring.gpg] \
https://packagecloud.io/timescale/timescaledb/${REPO_PATH}/ \
${OS_CODENAME} main" \
            | tee /etc/apt/sources.list.d/timescaledb.list
    else
        echo "[DRY RUN] Would add TimescaleDB repository"
    fi
else
    echo "TimescaleDB repository already configured."
fi

if [ "$DRY_RUN" = false ]; then
    apt-get update -qq
fi

# ============================================================
print_header "Step 4: Installing system packages"

PACKAGES="postgresql-16 postgresql-client-16 \
timescaledb-2-postgresql-16 timescaledb-tools redis-server \
python3-venv python3-pip traceroute iputils-tracepath iputils-ping libcap2-bin \
nodejs nginx certbot python3-certbot-nginx"

MISSING=""
for pkg in $PACKAGES; do
    if ! dpkg -l "$pkg" 2>/dev/null | grep -q "^ii"; then
        MISSING="$MISSING $pkg"
    fi
done

if [ -n "$MISSING" ]; then
    run "Installing packages: $MISSING" apt-get install -y $MISSING
else
    echo "All required packages already installed."
fi

# Enable unprivileged ICMP / raw socket capabilities for traceroute if available
TRACEROUTE_BIN=$(command -v traceroute || true)
if [ -n "$TRACEROUTE_BIN" ] && command -v setcap &>/dev/null; then
    run "Setting network capabilities for traceroute" setcap cap_net_raw+ep "$TRACEROUTE_BIN" || true
fi

# ============================================================
print_header "Step 5: Detecting Python version"

PYTHON_BIN=""
for ver in 3.13 3.12 3.11; do
    if command -v "python$ver" &>/dev/null; then
        PYTHON_BIN="python$ver"
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "Error: Python 3.11 or higher not found."
    echo "Install python3.11 or python3.12 before running this script."
    exit 1
fi

echo "Using $PYTHON_BIN ($($PYTHON_BIN --version))"

# ============================================================
print_header "Step 6: Creating system user and directories"

if id "netmon" &>/dev/null; then
    echo "User 'netmon' already exists."
else
    run "Creating system user 'netmon'" \
        useradd -r -s /usr/sbin/nologin netmon
fi

for dir in /opt/netmon "$CONFIG_DIR" "$LOG_DIR" "$BACKUP_DIR"; do
    if [ ! -d "$dir" ]; then
        run "Creating directory $dir" mkdir -p "$dir"
        run "Setting ownership: $dir" chown netmon:netmon "$dir"
    else
        echo "Directory $dir already exists."
    fi
done

# ============================================================
print_header "Step 7: Copying project files"

if [ ! -d "$INSTALL_DIR" ]; then
    run "Creating project directory $INSTALL_DIR" \
        mkdir -p "$INSTALL_DIR"
    run "Copying project files to $INSTALL_DIR" \
        rsync -a \
        --exclude='.git' \
        --exclude='frontend/node_modules' \
        --exclude='backend/venv' \
        --exclude='tests' \
        --exclude='pytest.ini' \
        --exclude='scratch' \
        "$PROJECT_ROOT/" "$INSTALL_DIR/"
    run "Setting project ownership" \
        chown -R netmon:netmon "$INSTALL_DIR"
else
    echo "Project files already exist at $INSTALL_DIR."
    echo "Updating project files..."
    run "Syncing project files" \
        rsync -a --delete \
        --exclude='.git' \
        --exclude='frontend/node_modules' \
        --exclude='backend/venv' \
        --exclude='tests' \
        --exclude='pytest.ini' \
        --exclude='scratch' \
        "$PROJECT_ROOT/" "$INSTALL_DIR/"
    run "Setting project ownership" \
        chown -R netmon:netmon "$INSTALL_DIR"
fi

run "Marking install directory as git safe directory" \
    git config --global --add safe.directory "$INSTALL_DIR"

# ============================================================
print_header "Step 8: Creating Python virtual environment"

if [ ! -d "$VENV_DIR" ]; then
    run "Creating virtual environment with $PYTHON_BIN" \
        $PYTHON_BIN -m venv "$VENV_DIR"
    run "Setting venv ownership" \
        chown -R netmon:netmon "$VENV_DIR"
fi

run "Upgrading pip to latest version" \
    sudo -H -u netmon "$VENV_DIR/bin/pip" install \
    --timeout 120 \
    --upgrade pip

run "Installing Python dependencies" \
    sudo -H -u netmon "$VENV_DIR/bin/pip" install \
    --timeout 120 \
    --retries 5 \
    -r "$INSTALL_DIR/backend/requirements.txt"

# ============================================================
print_header "Step 9: Building Vue frontend"

if [ ! -d "$INSTALL_DIR/frontend/node_modules" ]; then
    run "Installing frontend npm dependencies" \
        bash -c "cd $INSTALL_DIR/frontend && npm install --silent"
fi

run "Building Vue frontend for production" \
    bash -c "cd $INSTALL_DIR/frontend && npm run build"

run "Setting frontend ownership" \
    chown -R netmon:netmon "$INSTALL_DIR/frontend/dist"

# ============================================================
print_header "Step 10: Configuration"

if [ -f "$ENV_FILE" ]; then
    echo "Environment file already exists at $ENV_FILE."
    echo "Skipping configuration prompts."
    source "$ENV_FILE"
else
    if [ "$DRY_RUN" = false ]; then
        echo ""
        echo "Configuring Netmon Platform..."
        echo "These will be stored in $ENV_FILE"
        echo ""

        # Auto-generate DB password
        DB_PASS=$(openssl rand -base64 18 | tr -dc 'a-zA-Z0-9' | head -c 16)
        echo "Database password auto-generated."

        # Set default admin password to 'admin'
        ADMIN_PASS="admin"
        echo "Default admin password configured as 'admin'."

        SECRET_KEY=$(openssl rand -hex 32)
        echo "Secret key auto-generated."

        # Auto-detect IP address
        PRIMARY_IP=$(hostname -I | awk '{print $1}' 2>/dev/null || ip route get 1 2>/dev/null | awk '{print $NF;exit}' || echo "localhost")
        echo "Detected primary IP address: $PRIMARY_IP"
        DOMAIN_NAME=$PRIMARY_IP
        echo "Server domain/IP configured to: $DOMAIN_NAME"

        cat > "$ENV_FILE" <<EOF
NETMON_DB_PASSWORD=$DB_PASS
NETMON_SECRET_KEY=$SECRET_KEY
DOMAIN_NAME=$DOMAIN_NAME
DEFAULT_ADMIN_PASSWORD=$ADMIN_PASS
EOF
        chmod 640 "$ENV_FILE"
        chown root:netmon "$ENV_FILE"
        echo "Environment file created at $ENV_FILE"
    else
        DB_PASS="dryrun_password"
        ADMIN_PASS="admin"
        SECRET_KEY="dryrun_secret"
        DOMAIN_NAME="monitor.example.com"
        echo "[DRY RUN] Would auto-generate DB password, set admin password to 'admin', generate secret key, and auto-detect IP address"
    fi
fi

# Read values for subsequent steps
if [ "$DRY_RUN" = false ]; then
    DB_PASS=$(grep NETMON_DB_PASSWORD "$ENV_FILE" | cut -d'=' -f2-)
    SECRET_KEY=$(grep NETMON_SECRET_KEY "$ENV_FILE" | cut -d'=' -f2-)
    DOMAIN_NAME=$(grep DOMAIN_NAME "$ENV_FILE" | cut -d'=' -f2-)
    if grep -q DEFAULT_ADMIN_PASSWORD "$ENV_FILE"; then
        ADMIN_PASS=$(grep DEFAULT_ADMIN_PASSWORD "$ENV_FILE" | cut -d'=' -f2-)
    else
        ADMIN_PASS="admin"
    fi
else
    DB_PASS="dryrun_password"
    SECRET_KEY="dryrun_secret"
    DOMAIN_NAME="monitor.example.com"
    ADMIN_PASS="admin"
fi

# ============================================================
print_header "Step 11: Creating configuration file"

if [ ! -f "$CONFIG_FILE" ]; then
    run "Copying config template" \
        cp "$INSTALL_DIR/deploy/config.template.toml" "$CONFIG_FILE"
    run "Setting config ownership" \
        chown root:netmon "$CONFIG_FILE"
    run "Setting config permissions" \
        chmod 640 "$CONFIG_FILE"
    echo "Config file created at $CONFIG_FILE"
    echo "Review and edit $CONFIG_FILE if needed."
else
    echo "Config file already exists at $CONFIG_FILE"
fi

# ============================================================
print_header "Step 12: Setting up PostgreSQL"

if [ "$DRY_RUN" = false ]; then
    # Tune TimescaleDB
    if command -v timescaledb-tune &>/dev/null; then
        echo "--> Tuning PostgreSQL for TimescaleDB"
        timescaledb-tune --quiet --yes
        systemctl restart postgresql
    fi

    # Create database user
    DB_PASS_ESCAPED=$(echo "$DB_PASS" | sed "s/'/''/g")
    if ! sudo -u postgres psql -tAc \
        "SELECT 1 FROM pg_roles WHERE rolname='netmon_user'" \
        | grep -q 1; then
        echo "--> Creating PostgreSQL user 'netmon_user'"
        sudo -u postgres psql -c \
            "CREATE USER netmon_user WITH PASSWORD '$DB_PASS_ESCAPED';"
    else
        echo "PostgreSQL user 'netmon_user' already exists."
        # Update password in case it changed
        sudo -u postgres psql -c \
            "ALTER USER netmon_user WITH PASSWORD '$DB_PASS_ESCAPED';"
    fi

    # Create database
    if ! sudo -u postgres psql -tAc \
        "SELECT 1 FROM pg_database WHERE datname='netmon'" \
        | grep -q 1; then
        echo "--> Creating database 'netmon'"
        sudo -u postgres psql -c \
            "CREATE DATABASE netmon OWNER netmon_user;"
    else
        echo "Database 'netmon' already exists."
    fi

    # Enable TimescaleDB extension
    echo "--> Enabling TimescaleDB extension"
    sudo -u postgres psql -d netmon -c \
        "CREATE EXTENSION IF NOT EXISTS timescaledb;"
else
    echo "[DRY RUN] Would create PostgreSQL user, database, and TimescaleDB extension"
fi

# ============================================================
print_header "Step 13: Running database migrations"

run "Running Alembic migrations" \
    sudo -H -u netmon bash -c "
        export NETMON_DB_PASSWORD='$DB_PASS' &&
        export NETMON_SECRET_KEY='$SECRET_KEY' &&
        export PYTHONPATH='$INSTALL_DIR/backend' &&
        cd '$INSTALL_DIR/backend' &&
        '$VENV_DIR/bin/alembic' upgrade head
    "

# ============================================================
print_header "Step 14: Creating default admin user"

if [ "$DRY_RUN" = false ]; then
    run "Seeding default admin user" \
        sudo -u netmon \
            NETMON_DB_PASSWORD="$DB_PASS" \
            NETMON_SECRET_KEY="$SECRET_KEY" \
            DEFAULT_ADMIN_PASSWORD="$ADMIN_PASS" \
            PYTHONPATH="$INSTALL_DIR/backend" \
            "$VENV_DIR/bin/python3" -m app.seed_admin
else
    echo "[DRY RUN] Would create default admin user (admin / $ADMIN_PASS)"
fi

# ============================================================
print_header "Step 15: Installing systemd services"

for service in netmon-engine netmon-api; do
    src="$INSTALL_DIR/deploy/${service}.service"
    dst="/etc/systemd/system/${service}.service"
    if [ ! -f "$dst" ] || ! diff -q "$src" "$dst" > /dev/null 2>&1; then
        run "Installing $service" cp "$src" "$dst"
    else
        echo "$service already up to date."
    fi
done

run "Reloading systemd daemon" systemctl daemon-reload
run "Enabling Redis service" bash -c "systemctl enable redis-server 2>/dev/null || systemctl enable redis 2>/dev/null || true"
run "Enabling netmon-engine" systemctl enable netmon-engine
run "Enabling netmon-api" systemctl enable netmon-api

# ============================================================
print_header "Step 16: Configuring Nginx"

NGINX_CONF="/etc/nginx/sites-available/netmon"

if [ "$DRY_RUN" = false ]; then
    CERT_DIR="/etc/ssl/certs"
    KEY_DIR="/etc/ssl/private"
    mkdir -p "$CERT_DIR" "$KEY_DIR"
    
    if [ ! -f "$CERT_DIR/netmon.crt" ] || [ ! -f "$KEY_DIR/netmon.key" ]; then
        echo "--> Generating self-signed SSL certificate for $DOMAIN_NAME"
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout "$KEY_DIR/netmon.key" \
            -out "$CERT_DIR/netmon.crt" \
            -subj "/C=US/ST=State/L=City/O=Netmon/CN=$DOMAIN_NAME" 2>/dev/null
        chmod 600 "$KEY_DIR/netmon.key"
        chmod 644 "$CERT_DIR/netmon.crt"
        echo "Self-signed certificate generated successfully."
    else
        echo "SSL certificate and key already exist."
    fi
fi

if [ ! -f "$NGINX_CONF" ]; then
    if [ "$DRY_RUN" = false ]; then
        echo "--> Generating Nginx configuration for $DOMAIN_NAME"
        sed "s/YOUR_DOMAIN/$DOMAIN_NAME/g" \
            "$INSTALL_DIR/deploy/nginx.conf.template" \
            > "$NGINX_CONF"
        ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/netmon
        nginx -t && systemctl reload nginx
        echo "Nginx configuration applied."
    else
        echo "[DRY RUN] Would generate Nginx config for $DOMAIN_NAME"
    fi
else
    echo "Nginx configuration already exists."
fi

# ============================================================
print_header "Step 17: Configuring logrotate"

LOGROTATE_DST="/etc/logrotate.d/netmon"
if [ ! -f "$LOGROTATE_DST" ]; then
    run "Installing logrotate config" \
        cp "$INSTALL_DIR/deploy/logrotate.conf" "$LOGROTATE_DST"
else
    echo "Logrotate config already exists."
fi

# ============================================================
print_header "Step 18: Starting services"

run "Starting Redis service" bash -c "systemctl start redis-server 2>/dev/null || systemctl start redis 2>/dev/null || true"
run "Starting netmon-api" systemctl start netmon-api
run "Starting netmon-engine" systemctl start netmon-engine

# ============================================================
print_header "Installation Complete"

if [ "$DRY_RUN" = true ]; then
    echo "DRY RUN complete. No changes were made."
else
    echo ""
    echo "lnmp v3.1.0 is now running."
    echo ""
    echo "  Dashboard:  https://$DOMAIN_NAME"
    echo "  API docs:   https://$DOMAIN_NAME/api/docs"
    echo ""
    echo "--------------------------------------------------------"
    echo "  DEFAULT ADMIN CREDENTIALS"
    echo "  Username: admin"
    echo "  Password: $ADMIN_PASS"
    echo ""
    echo "  You will be required to change this password"
    echo "  on your first login."
    echo "--------------------------------------------------------"
    echo "  DATABASE CREDENTIALS"
    echo "  Username: netmon_user"
    echo "  Database: netmon"
    echo "  Stored in: $ENV_FILE"
    echo "--------------------------------------------------------"
    echo ""
    echo "  Service status:"
    echo "  systemctl status netmon-api"
    echo "  systemctl status netmon-engine"
    echo ""
    echo "  Logs:"
    echo "  journalctl -u netmon-api -f"
    echo "  journalctl -u netmon-engine -f"
    echo ""
fi
echo "========================================================"
