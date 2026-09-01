#!/usr/bin/env bash
# Install DiceCore as a service on a Raspberry Pi.
#
# Deliberately boring and re-runnable: it may be the second thing you try after the first
# attempt half-worked, and it must not make that worse.
set -euo pipefail

PREFIX=${PREFIX:-/opt/dicecore}
STATE=${STATE:-/var/lib/dicecore}
USER_NAME=${USER_NAME:-dicecore}
REPO_DIR=$(cd "$(dirname "$0")/.." && pwd)

[ "$(id -u)" -eq 0 ] || { echo "Run this with sudo."; exit 1; }

echo "==> Packages"
apt-get update -qq
# rpicam-apps: the capture fallback that works on every Bookworm Pi.
# python3-picamera2: faster capture, and a system package that cannot be pip-installed.
apt-get install -y --no-install-recommends \
  python3-venv python3-pip rpicam-apps python3-picamera2 libatlas-base-dev

echo "==> User and directories"
id -u "$USER_NAME" >/dev/null 2>&1 || useradd --system --home "$STATE" --shell /usr/sbin/nologin "$USER_NAME"
usermod -aG video "$USER_NAME"
install -d -o "$USER_NAME" -g "$USER_NAME" "$STATE" "$STATE/datasets" "$STATE/models" "$STATE/frames" "$STATE/tuning"

echo "==> Code in $PREFIX"
install -d "$PREFIX"
# Copy rather than symlink so a `git pull` in your working copy cannot half-update a
# running service.
cp -r "$REPO_DIR/src" "$REPO_DIR/pyproject.toml" "$REPO_DIR/README.md" "$REPO_DIR/LICENSE" "$PREFIX/"

echo "==> Virtualenv (with system site packages, for picamera2)"
python3 -m venv --system-site-packages "$PREFIX/.venv"
"$PREFIX/.venv/bin/pip" install --quiet --upgrade pip
# onnxruntime is left out on purpose: it has no ARMv6 wheel and is slow to build. Add it on
# a Pi 4/5 with: .venv/bin/pip install 'dicecore[model]'
"$PREFIX/.venv/bin/pip" install --quiet -e "$PREFIX[vision,server]"
chown -R "$USER_NAME:$USER_NAME" "$PREFIX"

echo "==> Tuning files"
if [ -d "$REPO_DIR/provisioning/tuning" ]; then
  cp "$REPO_DIR"/provisioning/tuning/*.json "$STATE/tuning/" 2>/dev/null || true
fi

echo "==> Service"
install -m 644 "$REPO_DIR/provisioning/dicecore.service" /etc/systemd/system/dicecore.service
systemctl daemon-reload
systemctl enable --now dicecore.service

PORT=$("$PREFIX/.venv/bin/python" - <<'PY'
from dicecore.config import Settings
print(Settings.load()[0].server.port)
PY
)
echo
echo "DiceCore is running: http://$(hostname).local:${PORT}/"
echo "Check what this Pi can do:  sudo -u $USER_NAME $PREFIX/.venv/bin/dicecore doctor"
echo "Pick a camera module:       sudo $PREFIX/.venv/bin/dicecore camera-module list"
