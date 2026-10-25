#!/usr/bin/env bash

# ============================================================
# SvxLink-LCD Installer
#
# Supports Raspberry Pi OS Bookworm and Debian 13 Trixie.
#
# Installs:
#   - Python virtual environment
#   - Adafruit LCD dependencies
#   - SvxLink-LCD systemd service
#
# Preserves existing LCD configuration and virtual environment.
#
# Does not alter SvxLink or SvxLink-Dash.
# ============================================================

set -Eeuo pipefail

APP_DIR="/opt/svxlink-lcd"
VENV_DIR="${APP_DIR}/venv"
SERVICE_NAME="svxlink-lcd.service"
SERVICE_SOURCE="${APP_DIR}/install/${SERVICE_NAME}"
SERVICE_DEST="/etc/systemd/system/${SERVICE_NAME}"

CONTROL_SERVICE="svxlink-lcd-control.service"
CONTROL_SOCKET="svxlink-lcd-control.socket"

CONTROL_SERVICE_SOURCE="${APP_DIR}/install/${CONTROL_SERVICE}"
CONTROL_SOCKET_SOURCE="${APP_DIR}/install/${CONTROL_SOCKET}"

SYSTEMD_DIR="/etc/systemd/system"

SERVICE_USER="pi"

echo
echo "=========================================="
echo " SvxLink-LCD Installer"
echo "=========================================="
echo

# ------------------------------------------------------------
# Root permissions
# ------------------------------------------------------------

if [[ "${EUID}" -ne 0 ]]; then
    echo "ERROR: Run this installer with sudo."
    exit 1
fi

# ------------------------------------------------------------
# Verify application files
# ------------------------------------------------------------

if [[ ! -f "${APP_DIR}/lcd_controller.py" ]]; then
    echo "ERROR: SvxLink-LCD application not found."
    echo "Clone the repository into ${APP_DIR} first."
    exit 1
fi

if [[ ! -f "${APP_DIR}/dtmf_control.py" ]]; then
    echo "ERROR: DTMF helper not found."
    exit 1
fi

if [[ ! -f "${APP_DIR}/config/lcd_config.json" ]]; then
    echo "ERROR: LCD configuration not found."
    exit 1
fi

if [[ ! -f "${SERVICE_SOURCE}" ]]; then
    echo "ERROR: systemd service template not found."
    exit 1
fi

if [[ ! -f "${APP_DIR}/lcd_control_service.py" ]]; then
    echo "ERROR: LCD control service script not found."
    exit 1
fi

if [[ ! -f "${CONTROL_SERVICE_SOURCE}" ]]; then
    echo "ERROR: LCD control systemd service not found."
    exit 1
fi

if [[ ! -f "${CONTROL_SOCKET_SOURCE}" ]]; then
    echo "ERROR: LCD control socket unit not found."
    exit 1
fi

if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
    echo "ERROR: Required user ${SERVICE_USER} does not exist."
    exit 1
fi

if ! id svxlink >/dev/null 2>&1; then
    echo "ERROR: The svxlink service account does not exist."
    echo "Install SvxLink before installing SvxLink-LCD."
    exit 1
fi

# ------------------------------------------------------------
# Install operating system dependencies
# ------------------------------------------------------------

echo "[1/7] Installing system dependencies..."

apt-get update

DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3 \
    python3-venv \
    python3-dev \
    python3-pip \
    build-essential \
    i2c-tools

# ------------------------------------------------------------
# Check I2C support
# ------------------------------------------------------------

echo "[2/7] Checking I2C..."

if [[ -e /dev/i2c-1 ]]; then
    echo "I2C device /dev/i2c-1 detected."
else
    echo "WARNING: /dev/i2c-1 not detected."
    echo "Enable I2C using raspi-config and reboot."
fi

if getent group i2c >/dev/null; then
    usermod -aG i2c "${SERVICE_USER}"
    echo "I2C group membership configured."
else
    echo "WARNING: I2C group not found."
    echo "Check the operating system I2C configuration."
fi

# ------------------------------------------------------------
# Application ownership and service access
# ------------------------------------------------------------

echo "Configuring application permissions..."

chown -R "${SERVICE_USER}:${SERVICE_USER}" "${APP_DIR}"

chmod 0755 "${APP_DIR}"

# The control helper runs as svxlink and needs read access
# to the application and its Python environment.
if ! runuser -u svxlink -- test -r \
    "${APP_DIR}/lcd_control_service.py"; then
    echo "ERROR: svxlink cannot read the control service."
    exit 1
fi
# ------------------------------------------------------------
# Create or preserve Python virtual environment
# ------------------------------------------------------------

echo "[3/7] Preparing Python environment..."

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then

    echo "Creating Python virtual environment..."

    python3 -m venv \
        --system-site-packages \
        "${VENV_DIR}"

else
    echo "Existing virtual environment preserved."
fi

# ------------------------------------------------------------
# Install Adafruit LCD library
# ------------------------------------------------------------

echo "[4/7] Installing LCD dependencies..."

"${VENV_DIR}/bin/python" -m pip install \
    adafruit-circuitpython-charlcd

# ------------------------------------------------------------
# Validate Python and configuration
# ------------------------------------------------------------

# ------------------------------------------------------------
# Prepare persistent LCD configuration
# ------------------------------------------------------------

CONFIG_DIR="/etc/svxlink-lcd"
CONFIG_FILE="${CONFIG_DIR}/lcd_config.json"
DEFAULT_CONFIG="${APP_DIR}/config/lcd_config.json"

echo "Preparing persistent LCD configuration..."

install -d -o root -g root -m 0755 \
    "${CONFIG_DIR}"

if [[ ! -f "${CONFIG_FILE}" ]]; then

    install -o root -g root -m 0644 \
        "${DEFAULT_CONFIG}" \
        "${CONFIG_FILE}"

    echo "Created ${CONFIG_FILE}"

else
    echo "Existing LCD configuration preserved."
fi

echo "[5/7] Validating application..."

"${VENV_DIR}/bin/python" -m py_compile \
    "${APP_DIR}/lcd_controller.py" \
    "${APP_DIR}/dtmf_control.py"

cd "${APP_DIR}"

"${VENV_DIR}/bin/python" - <<'PY'
import board
import adafruit_character_lcd.character_lcd_rgb_i2c

from dtmf_control import load_lcd_config

config = load_lcd_config()

print("Adafruit LCD library: OK")
print("LCD configuration: OK")
print("Configured node type:",
      config["control"]["node_type"])
PY

# ------------------------------------------------------------
# Install systemd service
# ------------------------------------------------------------

echo "[6/7] Installing systemd service..."

# Install the main LCD service.
install -o root -g root -m 0644 \
    "${SERVICE_SOURCE}" \
    "${SERVICE_DEST}"

# Install the restricted DTMF control service.
install -o root -g root -m 0644 \
    "${CONTROL_SERVICE_SOURCE}" \
    "${SYSTEMD_DIR}/${CONTROL_SERVICE}"

# Install the Unix socket unit.
install -o root -g root -m 0644 \
    "${CONTROL_SOCKET_SOURCE}" \
    "${SYSTEMD_DIR}/${CONTROL_SOCKET}"

systemctl daemon-reload

systemctl enable "${SERVICE_NAME}"
systemctl enable "${CONTROL_SOCKET}"

# ------------------------------------------------------------
# Start or restart LCD service
# ------------------------------------------------------------

echo "[7/7] Starting SvxLink-LCD..."

# The socket starts independently of the LCD display.
# Control remains preview-only at this stage.
systemctl restart "${CONTROL_SOCKET}"

systemctl restart "${SERVICE_NAME}"

echo
echo "=========================================="
echo " Installation completed"
echo "=========================================="
echo

systemctl --no-pager --full status \
    "${SERVICE_NAME}" || true

echo
echo "Application: ${APP_DIR}"
echo "Configuration: ${APP_DIR}/config/lcd_config.json"
echo "Service: ${SERVICE_NAME}"
echo

echo "Check logs using:"
echo "sudo journalctl -u ${SERVICE_NAME} -f"
echo
echo "NOTE: Ensure I2C is enabled and the LCD plate"
echo "is connected before using the display."
echo
echo "DTMF control remains in preview-only mode."
echo
