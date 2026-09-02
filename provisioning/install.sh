#!/usr/bin/env bash
#
# Install DiceCore. Run it from a checkout:
#
#   sudo bash provisioning/install.sh              # works out what this machine is
#   sudo bash provisioning/install.sh --role desk  # a training machine (PyTorch, no service)
#   sudo bash provisioning/install.sh --role pi    # a tower (camera stack, systemd service)
#   sudo bash provisioning/install.sh --no-service
#
# Deliberately boring and re-runnable: it may well be the second thing you try after the
# first attempt half-worked, and it must not make that worse.
set -euo pipefail

ROLE=""
WANT_SERVICE=1
for arg in "$@"; do
  case "$arg" in
    --role) shift ;;
    pi|desk) ROLE="$arg" ;;
    --role=*) ROLE="${arg#*=}" ;;
    --no-service) WANT_SERVICE=0 ;;
    *) ;;
  esac
done

REPO_DIR=$(cd "$(dirname "$0")/.." && pwd)
STATE=${STATE:-/var/lib/dicecore}
USER_NAME=${USER_NAME:-dicecore}
VENV="$REPO_DIR/.venv"

[ "$(id -u)" -eq 0 ] || { echo "Run this with sudo."; exit 1; }

# --- which machine is this? -------------------------------------------------
IS_PI=0
if grep -qi "raspberry pi" /proc/device-tree/model 2>/dev/null; then IS_PI=1; fi
[ -z "$ROLE" ] && { [ "$IS_PI" -eq 1 ] && ROLE=pi || ROLE=desk; }
ARCH=$(uname -m)

echo "== DiceCore install =="
echo "   role       : $ROLE"
echo "   machine    : $ARCH $( [ "$IS_PI" -eq 1 ] && cat /proc/device-tree/model | tr -d '\0' )"
echo "   checkout   : $REPO_DIR"

# --- packages ---------------------------------------------------------------
echo "-- packages"
apt-get update -qq
BASE="python3-venv python3-pip git"
if [ "$ROLE" = pi ]; then
  # rpicam-apps: the capture fallback that works on every Bookworm Pi.
  # python3-picamera2: faster capture, and a system package that cannot be pip-installed.
  # libatlas-base-dev: numpy's BLAS on a Pi.
  # network-manager, rfkill, iw: the setup page manages WiFi through nmcli and reads the
  # radio through the other two. Without them a box that loses its network has no way back.
  apt-get install -y --no-install-recommends $BASE rpicam-apps python3-picamera2 \
    libatlas-base-dev network-manager rfkill iw
else
  apt-get install -y --no-install-recommends $BASE
fi

# --- extras: only what this machine can use ---------------------------------
# ARMv6 (Pi Zero v1) has no wheels for OpenCV or onnxruntime, so it gets the bare package
# and reads through another machine (engine.mode=remote). Saying that here is kinder than
# a wall of build errors.
EXTRAS="vision,server"
if [ "$ARCH" = "armv6l" ]; then
  EXTRAS=""
  echo "   note       : ARMv6 — capture only; set engine.mode=remote and point it at a PC"
elif [ "$ROLE" = desk ]; then
  EXTRAS="vision,server,train,display,gpio"
else
  EXTRAS="vision,server,model,display,gpio"
fi
echo "   extras     : ${EXTRAS:-none}"

# --- user and directories ---------------------------------------------------
if [ "$ROLE" = pi ]; then
  echo "-- user and directories"
  id -u "$USER_NAME" >/dev/null 2>&1 || useradd --system --home "$STATE" --shell /usr/sbin/nologin "$USER_NAME"
  usermod -aG video,gpio,spi,i2c "$USER_NAME" 2>/dev/null || usermod -aG video "$USER_NAME"
  install -d -o "$USER_NAME" -g "$USER_NAME" "$STATE" "$STATE/datasets" "$STATE/models" \
          "$STATE/frames" "$STATE/tuning"
fi

# --- virtualenv -------------------------------------------------------------
echo "-- virtualenv at $VENV"
if [ "$ROLE" = pi ]; then
  # --system-site-packages so the venv can see python3-picamera2, which is apt-only.
  python3 -m venv --system-site-packages "$VENV"
else
  python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install --quiet --upgrade pip
if [ -n "$EXTRAS" ]; then
  "$VENV/bin/pip" install --quiet -e "$REPO_DIR[$EXTRAS]"
else
  "$VENV/bin/pip" install --quiet -e "$REPO_DIR"
fi

if [ "$ROLE" = pi ]; then
  [ -d "$REPO_DIR/provisioning/tuning" ] && \
    cp "$REPO_DIR"/provisioning/tuning/*.json "$STATE/tuning/" 2>/dev/null || true
  chown -R "$USER_NAME:$USER_NAME" "$VENV" 2>/dev/null || true
fi

# --- something to look at before any hardware arrives -----------------------
echo "-- a few rendered rolls, so the simulator has something to read"
if [ "$ROLE" = pi ]; then
  sudo -u "$USER_NAME" DICECORE_STATE="$STATE" "$VENV/bin/dicecore" synth --count 12 >/dev/null || true
else
  "$VENV/bin/dicecore" synth --count 12 >/dev/null || true
fi

# --- the way back in --------------------------------------------------------
if [ "$ROLE" = pi ]; then
  echo "-- network"
  # A Pi refuses to transmit until it knows which country's rules apply, and says so as
  # "device is not available" — the most common reason a fresh Pi's hotspot never appears.
  if command -v raspi-config >/dev/null; then
    CC=$(raspi-config nonint get_wifi_country 2>/dev/null || true)
    if [ -z "$CC" ] || [ "$CC" = "0" ]; then
      echo "   !! no WiFi country set — the radio will stay blocked until one is."
      echo "      Set it on the Network page, or: sudo raspi-config nonint do_wifi_country DE"
    else
      echo "   WiFi country: $CC"
    fi
  fi
  # The service runs as root so it can manage the network and bind port 80 for the captive
  # portal. That is the trade: a box nobody can reach is worse than a service with rights.
  install -d /etc/NetworkManager/dnsmasq-shared.d
fi

# --- service ----------------------------------------------------------------
if [ "$ROLE" = pi ] && [ "$WANT_SERVICE" -eq 1 ]; then
  echo "-- service"
  sed "s|/opt/dicecore|$REPO_DIR|g" "$REPO_DIR/provisioning/dicecore.service" \
    > /etc/systemd/system/dicecore.service
  systemctl daemon-reload
  systemctl enable --now dicecore.service
fi

PORT=$("$VENV/bin/python" - <<'PY'
from dicecore.config import Settings
print(Settings.load()[0].server.port)
PY
)

echo
echo "== done =="
if [ "$ROLE" = pi ] && [ "$WANT_SERVICE" -eq 1 ]; then
  echo "   game screen : http://$(hostname).local:${PORT}/"
  echo "   setup       : http://$(hostname).local:${PORT}/setup"
  echo "   what this Pi can do:  sudo -u $USER_NAME $VENV/bin/dicecore doctor"
  echo "   pick a camera module: sudo $VENV/bin/dicecore camera-module list"
else
  echo "   start it with:  $VENV/bin/dicecore serve"
  echo "   then open    :  http://localhost:${PORT}/"
  [ "$ROLE" = desk ] && echo "   PyTorch is installed, so this machine can train models."
fi
