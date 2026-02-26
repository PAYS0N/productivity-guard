#!/bin/bash
# setup_doh_block.sh — Create dnsmasq config to block DNS-over-HTTPS providers
#
# This prevents browsers (especially Firefox) from bypassing local DNS blocking
# by using encrypted DNS. Two mechanisms:
#
# 1. Canary domain: Firefox checks "use-application-dns.net" — if it gets NXDOMAIN,
#    Firefox automatically disables DoH. This is Mozilla's official opt-out mechanism.
#    We return NXDOMAIN via a bogus address directive that won't resolve.
#
# 2. Block DoH provider hostnames: Even if the canary is somehow bypassed, the
#    browser can't reach DoH servers if their hostnames resolve to 0.0.0.0.
#    Firefox resolves the DoH endpoint via system DNS first (bootstrap step),
#    so blocking the hostname here prevents the connection.
#
# This file is separate from blocked_hosts (which is managed dynamically by the
# backend for site blocking/unblocking). This file is static and should never
# be modified by the backend.
#
# Usage:
#   chmod +x setup_doh_block.sh
#   ./setup_doh_block.sh
#
# To update the DoH provider list later, edit this script and re-run it.

set -e

DOH_CONF="/etc/dnsmasq.d/doh_block.conf"
DNSMASQ_NEEDS_RESTART=false

echo "=== DoH Block Setup ==="

# Check if already exists
if [ -f "$DOH_CONF" ]; then
    echo "Existing $DOH_CONF found. Overwriting..."
fi

cat <<'EOF' | sudo tee "$DOH_CONF" > /dev/null
# Managed by Productivity Guard — block DNS-over-HTTPS providers
# This prevents browsers from bypassing local DNS filtering.
# Re-generate with: ./setup_doh_block.sh

# ── Firefox canary domain ───────────────────────────────────────────────────
# Firefox checks this domain on startup. If it fails to resolve, Firefox
# automatically disables DoH. This is Mozilla's official network opt-out.
# We return NXDOMAIN by not giving it any address.
server=/use-application-dns.net/

# ── Major DoH providers ─────────────────────────────────────────────────────
# Block the hostnames browsers use to reach DoH servers. Since the browser
# must bootstrap-resolve these via system DNS, returning 0.0.0.0 prevents
# the DoH connection from ever being established.

# Cloudflare (Firefox default)
address=/mozilla.cloudflare-dns.com/0.0.0.0
address=/cloudflare-dns.com/0.0.0.0
address=/dns.cloudflare.com/0.0.0.0
address=/one.one.one.one/0.0.0.0

# Google
address=/dns.google/0.0.0.0
address=/dns.google.com/0.0.0.0
address=/dns64.dns.google/0.0.0.0

# Quad9
address=/dns.quad9.net/0.0.0.0
address=/dns9.quad9.net/0.0.0.0
address=/dns10.quad9.net/0.0.0.0
address=/dns11.quad9.net/0.0.0.0

# OpenDNS / Cisco
address=/doh.opendns.com/0.0.0.0
address=/dns.umbrella.com/0.0.0.0

# NextDNS
address=/dns.nextdns.io/0.0.0.0
address=/firefox.dns.nextdns.io/0.0.0.0
address=/chrome.dns.nextdns.io/0.0.0.0

# Mullvad
address=/dns.mullvad.net/0.0.0.0
address=/doh.mullvad.net/0.0.0.0

# AdGuard DNS (the public DNS service, not AdGuard Home)
address=/dns.adguard-dns.com/0.0.0.0
address=/dns-unfiltered.adguard.com/0.0.0.0

# CleanBrowsing
address=/doh.cleanbrowsing.org/0.0.0.0

# Comcast / Xfinity
address=/doh.xfinity.com/0.0.0.0

# Control D
address=/freedns.controld.com/0.0.0.0

# Apple (iCloud Private Relay uses DoH-like resolution)
address=/doh.dns.apple.com/0.0.0.0
address=/mask.icloud.com/0.0.0.0
address=/mask-h2.icloud.com/0.0.0.0
EOF

echo "  ✓ Created $DOH_CONF"

# Restart dnsmasq to pick up the new config
echo "Restarting dnsmasq..."
sudo systemctl restart dnsmasq
echo "  ✓ dnsmasq restarted"

echo ""
echo "=== DoH blocking active ==="
echo "Firefox should auto-disable DoH on next startup (canary domain)."
echo "Other browsers will fail to reach DoH providers (hostname blocking)."
echo ""
echo "To verify Firefox canary works:"
echo "  dig use-application-dns.net @192.168.22.1"
echo "  (should return NXDOMAIN or empty)"
echo ""
echo "To verify provider blocking:"
echo "  dig mozilla.cloudflare-dns.com @192.168.22.1"
echo "  (should return 0.0.0.0)"