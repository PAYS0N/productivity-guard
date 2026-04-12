#!/bin/bash
# Productivity Guard — Setup Script
#
# Run this on the Pi as your normal user (pays0n).
# It will:
# 1. Swap dnsmasq addn-hosts → hostsdir directive
# 2. Add local-ttl=5 to dnsmasq config (short TTL for blocked responses)
# 3. Set up DoH blocking
# 4. Create the initial blocked_hosts file
# 5. Add iptables rule for port 8800
# 6. Install Docker and Docker Compose if absent
# 7. Create .env from .env.example if absent
# 8. Migrate existing SQLite database into the Docker volume if present
# 9. Create config.yaml from the example if absent
# 10. Start the backend container
#
# Prerequisites:
# - dnsmasq running
# - iptables-persistent installed

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
DNSMASQ_CONF="/etc/dnsmasq.d/router.conf"
BLOCKED_HOSTS_DIR="/etc/productivity-guard"
BLOCKED_HOSTS="$BLOCKED_HOSTS_DIR/blocked_hosts"
LEGACY_DB="/home/pays0n/productivity-guard/requests.db"

echo "=== Productivity Guard Setup ==="
echo ""

# ── 1. dnsmasq hostsdir ────────────────────────────────────────────────────

echo "[1/10] Configuring dnsmasq hostsdir..."

# Remove legacy addn-hosts line if present
if grep -q "addn-hosts=$BLOCKED_HOSTS" "$DNSMASQ_CONF" 2>/dev/null; then
    sudo sed -i "\|addn-hosts=$BLOCKED_HOSTS|d" "$DNSMASQ_CONF"
    echo "  ✓ Removed legacy addn-hosts directive"
fi

if ! grep -q "hostsdir=$BLOCKED_HOSTS_DIR" "$DNSMASQ_CONF" 2>/dev/null; then
    echo "" | sudo tee -a "$DNSMASQ_CONF" > /dev/null
    echo "# Productivity Guard blocked domains" | sudo tee -a "$DNSMASQ_CONF" > /dev/null
    echo "hostsdir=$BLOCKED_HOSTS_DIR" | sudo tee -a "$DNSMASQ_CONF" > /dev/null
    echo "  ✓ Added hostsdir directive to $DNSMASQ_CONF"
else
    echo "  ✓ hostsdir already configured"
fi

# ── 2. dnsmasq local-ttl ───────────────────────────────────────────────────

echo "[2/10] Setting short DNS TTL for blocked responses..."
if ! grep -q "local-ttl=5" "$DNSMASQ_CONF" 2>/dev/null; then
    echo "local-ttl=5" | sudo tee -a "$DNSMASQ_CONF" > /dev/null
    echo "  ✓ Added local-ttl=5 to $DNSMASQ_CONF"
else
    echo "  ✓ local-ttl already configured"
fi

# ── 3. DoH blocking ────────────────────────────────────────────────────────

echo "[3/10] Setting up DoH blocking..."
bash "$SCRIPT_DIR/setup_doh_block.sh"

# ── 4. Initial blocked_hosts ───────────────────────────────────────────────

echo "[4/10] Creating initial blocked_hosts file..."
sudo mkdir -p "$BLOCKED_HOSTS_DIR"
if [ ! -f "$BLOCKED_HOSTS" ]; then
    cat <<'EOF' | sudo tee "$BLOCKED_HOSTS" > /dev/null
# Managed by Productivity Guard — do not edit manually
0.0.0.0 reddit.com
0.0.0.0 www.reddit.com
0.0.0.0 youtube.com
0.0.0.0 www.youtube.com
0.0.0.0 inv.nadeko.net
0.0.0.0 yewtu.be
0.0.0.0 invidious.nerdvpn.de
EOF
    echo "  ✓ Created $BLOCKED_HOSTS"
else
    echo "  ✓ $BLOCKED_HOSTS already exists"
fi

# ── 5. iptables rule ───────────────────────────────────────────────────────

echo "[5/10] Adding iptables rule for port 8800..."
if ! sudo iptables -C INPUT -s 192.168.22.0/24 -i wlan0 -p tcp -m tcp --dport 8800 -j ACCEPT 2>/dev/null; then
    RULE_NUM=$(sudo iptables -L INPUT --line-numbers -n | grep "dpt:8123" | awk '{print $1}')
    if [ -n "$RULE_NUM" ]; then
        INSERT_AT=$((RULE_NUM + 1))
        sudo iptables -I INPUT "$INSERT_AT" -s 192.168.22.0/24 -i wlan0 -p tcp -m tcp --dport 8800 -j ACCEPT
    else
        sudo iptables -A INPUT -s 192.168.22.0/24 -i wlan0 -p tcp -m tcp --dport 8800 -j ACCEPT
    fi
    sudo netfilter-persistent save
    echo "  ✓ Added iptables rule and saved"
else
    echo "  ✓ iptables rule already exists"
fi

# ── 6. Docker ──────────────────────────────────────────────────────────────

echo "[6/10] Checking Docker installation..."
if ! command -v docker &>/dev/null; then
    echo "  Installing Docker..."
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "$USER"
    echo "  ✓ Docker installed. You may need to log out and back in for group membership to take effect."
else
    echo "  ✓ Docker already installed"
fi

if ! docker compose version &>/dev/null; then
    echo "  Installing Docker Compose plugin..."
    sudo apt-get install -y docker-compose-plugin
    echo "  ✓ Docker Compose installed"
else
    echo "  ✓ Docker Compose already installed"
fi

# ── 7. .env file ───────────────────────────────────────────────────────────

echo "[7/10] Checking .env file..."
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
    echo "  ⚠ Created .env from .env.example. YOU MUST EDIT IT:"
    echo "    - Set ANTHROPIC_API_KEY"
    echo "    - Set HA_TOKEN"
    echo "    Edit: $SCRIPT_DIR/.env"
else
    echo "  ✓ .env exists"
fi

# ── 8. Migrate existing SQLite database ────────────────────────────────────

echo "[8/10] Checking for existing database to migrate..."
VOLUME_NAME="prod-guard_pg-data"
VOLUME_PATH="/var/lib/docker/volumes/${VOLUME_NAME}/_data"

if [ -f "$LEGACY_DB" ]; then
    # Ensure volume exists by creating it if needed
    docker volume inspect "$VOLUME_NAME" &>/dev/null || docker volume create "$VOLUME_NAME" > /dev/null
    sudo mkdir -p "$VOLUME_PATH"

    if [ ! -f "$VOLUME_PATH/requests.db" ]; then
        sudo cp "$LEGACY_DB" "$VOLUME_PATH/requests.db"
        echo "  ✓ Migrated $LEGACY_DB → Docker volume ($VOLUME_PATH/requests.db)"
    else
        echo "  ✓ Volume already contains requests.db — skipping migration"
    fi
else
    echo "  ✓ No legacy database found at $LEGACY_DB — starting fresh"
fi

# ── 9. Config file ─────────────────────────────────────────────────────────

echo "[9/10] Checking config..."
if [ ! -f "$BACKEND_DIR/config.yaml" ]; then
    cp "$BACKEND_DIR/config.example.yaml" "$BACKEND_DIR/config.yaml"
    echo "  ⚠ Created config.yaml from example. YOU MUST EDIT IT:"
    echo "    - Verify Bermuda entity names"
    echo "    Edit: $BACKEND_DIR/config.yaml"
else
    echo "  ✓ config.yaml exists"
fi

# ── Restart dnsmasq ─────────────────────────────────────────────────────────

echo ""
echo "Restarting dnsmasq..."
sudo systemctl restart dnsmasq
echo "  ✓ dnsmasq restarted"

# ── 10. Start container ────────────────────────────────────────────────────

echo "[10/10] Starting backend container..."
cd "$SCRIPT_DIR"
docker compose up -d --build
echo "  ✓ Backend container started"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit $SCRIPT_DIR/.env with your API keys (if not already done)"
echo "  2. Edit $BACKEND_DIR/config.yaml to verify Bermuda entity names"
echo "  3. Check logs:"
echo "     cd $SCRIPT_DIR && docker compose logs -f"
echo "  4. Restart the container after config changes:"
echo "     cd $SCRIPT_DIR && docker compose restart"
echo "  5. Install the Firefox extension:"
echo "     Open about:debugging → Load Temporary Add-on → select extension/manifest.json"
echo "  6. Add HA automations from homeassistant/automations.yaml"
echo ""
