#!/usr/bin/env bash
# ===========================================================================
# Tesla Journey OS — WiFi Monitor
#
# Monitors WiFi connection health. When the Pi loses WiFi connectivity,
# starts a fallback access point so users can still connect in-car.
# When WiFi returns, tears down the AP.
#
# Designed to run as a systemd service.
# ===========================================================================
set -euo pipefail

APP_DIR="/opt/tesla-journey-os"
VENV_DIR="${APP_DIR}/venv"
CONFIG_FILE="${APP_DIR}/config.yaml"

# Defaults (overridden by config.yaml when available)
AP_SSID="${AP_SSID:-Tesla Journey OS}"
AP_PASSPHRASE="${AP_PASSPHRASE:-}"
AP_CHANNEL="${AP_CHANNEL:-6}"
AP_INTERFACE="${AP_INTERFACE:-wlan0}"
CHECK_INTERVAL="${CHECK_INTERVAL:-20}"
DISCONNECT_GRACE="${DISCONNECT_GRACE:-30}"
MIN_RSSI="${MIN_RSSI:--70}"
STABLE_SECONDS="${STABLE_SECONDS:-20}"
PING_TARGET="${PING_TARGET:-8.8.8.8}"
RETRY_SECONDS="${RETRY_SECONDS:-300}"

AP_ACTIVE=0
CONSECUTIVE_GOOD=0
OFFLINE_SINCE=0

log() { echo "[wifi-monitor] $(date '+%H:%M:%S') $1"; }

# ── Check WiFi connection ──
check_wifi() {
    # Check if connected via nmcli
    if command -v nmcli &>/dev/null; then
        local state
        state=$(nmcli -t -f STATE general 2>/dev/null | head -1 || echo "unknown")
        if [ "$state" = "connected" ]; then
            # Check RSSI
            local rssi
            rssi=$(nmcli -t -f IN-USE,SIGNAL dev wifi 2>/dev/null | grep '^\*:' | cut -d: -f2 || echo "0")
            if [ -n "$rssi" ] && [ "$rssi" -gt "$MIN_RSSI" ] 2>/dev/null; then
                return 0  # Good signal
            fi
        fi
    fi

    # Fallback: ping test
    if ping -c 1 -W 3 "$PING_TARGET" &>/dev/null; then
        return 0
    fi

    return 1  # No connectivity
}

# ── Start Access Point ──
start_ap() {
    if [ "$AP_ACTIVE" -eq 1 ]; then return; fi

    log "Starting fallback AP: $AP_SSID"

    # Configure hostapd
    cat > /tmp/tjos-hostapd.conf << HOSTAPD_EOF
interface=${AP_INTERFACE}
driver=nl80211
ssid=${AP_SSID}
hw_mode=g
channel=${AP_CHANNEL}
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
HOSTAPD_EOF

    # Add WPA2 if passphrase is set
    if [ -n "$AP_PASSPHRASE" ] && [ ${#AP_PASSPHRASE} -ge 8 ]; then
        cat >> /tmp/tjos-hostapd.conf << HOSTAPD_EOF
wpa=2
wpa_passphrase=${AP_PASSPHRASE}
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
HOSTAPD_EOF
    fi

    # Configure dnsmasq for DHCP + captive portal
    cat > /tmp/tjos-dnsmasq.conf << DNS_EOF
interface=${AP_INTERFACE}
dhcp-range=192.168.4.10,192.168.4.50,255.255.255.0,12h
dhcp-option=3,192.168.4.1
dhcp-option=6,192.168.4.1
address=/#/192.168.4.1
DNS_EOF

    # Assign static IP
    ip addr add 192.168.4.1/24 dev "$AP_INTERFACE" 2>/dev/null || true

    # Start services
    systemctl stop hostapd dnsmasq 2>/dev/null || true
    sleep 1
    hostapd -B /tmp/tjos-hostapd.conf 2>/dev/null || true
    dnsmasq -C /tmp/tjos-dnsmasq.conf 2>/dev/null || true

    AP_ACTIVE=1
    log "AP is active — connect to '$AP_SSID' and open any browser"
}

# ── Stop Access Point ──
stop_ap() {
    if [ "$AP_ACTIVE" -eq 0 ]; then return; fi

    log "Stopping AP..."
    killall hostapd 2>/dev/null || true
    killall dnsmasq 2>/dev/null || true
    ip addr del 192.168.4.1/24 dev "$AP_INTERFACE" 2>/dev/null || true

    AP_ACTIVE=0
    CONSECUTIVE_GOOD=0
    log "AP stopped"
}

# ── Cleanup on exit ──
cleanup() {
    stop_ap
    rm -f /tmp/tjos-hostapd.conf /tmp/tjos-dnsmasq.conf
    exit 0
}
trap cleanup SIGTERM SIGINT

# ── Main loop ──
log "WiFi monitor started (check every ${CHECK_INTERVAL}s)"
log "  SSID: $AP_SSID"
log "  Ping: $PING_TARGET"
log "  RSSI threshold: $MIN_RSSI dBm"

while true; do
    if check_wifi; then
        CONSECUTIVE_GOOD=$((CONSECUTIVE_GOOD + 1))
        OFFLINE_SINCE=0

        if [ "$CONSECUTIVE_GOOD" -ge "$((STABLE_SECONDS / CHECK_INTERVAL))" ]; then
            if [ "$AP_ACTIVE" -eq 1 ]; then
                stop_ap
            fi
        fi
    else
        CONSECUTIVE_GOOD=0
        if [ "$OFFLINE_SINCE" -eq 0 ]; then
            OFFLINE_SINCE=$(date +%s)
        fi

        local offline_dur=$(($(date +%s) - OFFLINE_SINCE))
        if [ "$offline_dur" -ge "$DISCONNECT_GRACE" ]; then
            start_ap
        fi
    fi

    sleep "$CHECK_INTERVAL"
done
