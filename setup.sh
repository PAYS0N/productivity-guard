#!/bin/bash
# Productivity Guard — Setup Script
#
# Run this on the Pi as your normal user (pays0n).
# It will:
# 1. Create a Python virtual environment and install dependencies
# 2. Add the addn-hosts directive to dnsmasq config
# 3. Add local-ttl=5 to dnsmasq config (short TTL for blocked responses)
# 4. Set up DoH blocking
# 5. Create the initial blocked_hosts file
# 6. Add iptables rule for port 8800
# 7. Create sudoers entry for blocklist management
# 8. Install and enable the systemd service
# 9. Create config.yaml from the example if it doesn't exist
#
# Prerequisites:
# - Python 3.11+ installed
# - dnsmasq running
# - iptables-persistent installed

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
VENV_DIR="$SCRIPT_DIR/venv"
DNSMASQ_CONF="/etc/dnsmasq.d/router.conf"
BLOCKED_HOSTS="/etc/productivity-guard/blocked_hosts"
SERVICE_FILE="/etc/systemd/system/productivity-guard.service"

echo "=== Productivity Guard Setup ==="
echo ""

# ── 1. Python venv ──────────────────────────────────────────────────────────

echo "[1/8] Setting up Python virtual environment..."
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r "$BACKEND_DIR/requirements.txt"
deactivate
echo "  ✓ Virtual environment ready at $VENV_DIR"

# ── 2. dnsmasq addn-hosts ──────────────────────────────────────────────────

echo "[2/8] Configuring dnsmasq addn-hosts..."
if ! grep -q "addn-hosts=$BLOCKED_HOSTS" "$DNSMASQ_CONF" 2>/dev/null; then
    echo "" | sudo tee -a "$DNSMASQ_CONF" > /dev/null
    echo "# Productivity Guard blocked domains" | sudo tee -a "$DNSMASQ_CONF" > /dev/null
    echo "addn-hosts=$BLOCKED_HOSTS" | sudo tee -a "$DNSMASQ_CONF" > /dev/null
    echo "  ✓ Added addn-hosts directive to $DNSMASQ_CONF"
else
    echo "  ✓ addn-hosts already configured"
fi

# ── 3. dnsmasq local-ttl ───────────────────────────────────────────────────

echo "[3/8] Setting short DNS TTL for blocked responses..."
if ! grep -q "local-ttl=5" "$DNSMASQ_CONF" 2>/dev/null; then
    echo "local-ttl=5" | sudo tee -a "$DNSMASQ_CONF" > /dev/null
    echo "  ✓ Added local-ttl=5 to $DNSMASQ_CONF"
else
    echo "  ✓ local-ttl already configured"
fi

# ── 4. DoH blocking ────────────────────────────────────────────────────────

echo "[4/9] Setting up DoH blocking..."
bash "$SCRIPT_DIR/setup_doh_block.sh"

# ── 5. Initial blocked_hosts ───────────────────────────────────────────────

echo "[5/9] Creating initial blocked_hosts file..."
sudo mkdir -p "$(dirname "$BLOCKED_HOSTS")"
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

# ── 6. iptables rule ───────────────────────────────────────────────────────

echo "[6/9] Adding iptables rule for port 8800..."
if ! sudo iptables -C INPUT -s 192.168.22.0/24 -i wlan0 -p tcp -m tcp --dport 8800 -j ACCEPT 2>/dev/null; then
    # Insert after the existing port 8123 rule
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

# ── 7. sudoers entry ───────────────────────────────────────────────────────

echo "[7/9] Creating sudoers entry for blocklist management..."
SUDOERS_FILE="/etc/sudoers.d/productivity-guard"
if [ ! -f "$SUDOERS_FILE" ]; then
    cat <<EOF | sudo tee "$SUDOERS_FILE" > /dev/null
# Productivity Guard — allow backend to manage DNS blocklist
pays0n ALL=(ALL) NOPASSWD: /usr/bin/tee /etc/productivity-guard/blocked_hosts
pays0n ALL=(ALL) NOPASSWD: /usr/bin/pkill -HUP dnsmasq
EOF
    sudo chmod 0440 "$SUDOERS_FILE"
    echo "  ✓ Created $SUDOERS_FILE"
else
    echo "  ✓ sudoers entry already exists"
fi

# ── 8. systemd service ─────────────────────────────────────────────────────

echo "[8/9] Installing systemd service..."
sudo cp "$BACKEND_DIR/productivity-guard.service" "$SERVICE_FILE"
sudo systemctl daemon-reload
sudo systemctl enable productivity-guard
echo "  ✓ Service installed and enabled"

# ── 9. Config file ─────────────────────────────────────────────────────────

echo "[9/9] Checking config..."
if [ ! -f "$BACKEND_DIR/config.yaml" ]; then
    cp "$BACKEND_DIR/config.example.yaml" "$BACKEND_DIR/config.yaml"
    echo "  ⚠ Created config.yaml from example. YOU MUST EDIT IT:"
    echo "    - Set your Anthropic API key"
    echo "    - Set your Home Assistant long-lived access token"
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

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit $BACKEND_DIR/config.yaml with your API keys"
echo "  2. Verify Bermuda entity names in config.yaml match your HA setup"
echo "  3. Start the service:"
echo "     sudo systemctl start productivity-guard"
echo "  4. Check logs:"
echo "     sudo journalctl -u productivity-guard -f"
echo "  5. Install the Firefox extension:"
echo "     Open about:debugging → Load Temporary Add-on → select extension/manifest.json"
echo "  6. Add HA automations from homeassistant/automations.yaml"
echo ""
