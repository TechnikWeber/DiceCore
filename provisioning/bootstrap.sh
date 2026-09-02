#!/usr/bin/env bash
#
# DiceCore one-line bootstrap: clone (or update) the repo and run the installer.
#
#   curl -fsSL https://raw.githubusercontent.com/TechnikWeber/DiceCore/main/provisioning/bootstrap.sh | bash
#
# Works on a Raspberry Pi and on an ordinary Linux desktop; the installer works out which
# it is on and installs what that machine can actually use. Add a role to force it:
#
#   … | bash -s -- --role desk    # a training machine: PyTorch, no service
#   … | bash -s -- --role pi      # a tower: camera stack and a systemd service
#
set -euo pipefail

REPO_URL="${DICECORE_REPO_URL:-https://github.com/TechnikWeber/DiceCore.git}"
DEST="${DICECORE_DEST:-/opt/dicecore}"

echo "== DiceCore bootstrap =="

if ! command -v git >/dev/null; then
  echo "-- installing git"
  sudo apt-get update && sudo apt-get install -y git
fi

if [ -d "$DEST/.git" ]; then
  echo "-- updating existing checkout at $DEST"
  sudo git -C "$DEST" pull --ff-only
else
  echo "-- cloning into $DEST"
  sudo mkdir -p "$DEST"
  sudo chown "$USER" "$DEST"
  git clone "$REPO_URL" "$DEST"
fi

echo "-- running installer"
sudo bash "$DEST/provisioning/install.sh" "$@"
