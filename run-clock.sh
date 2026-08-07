#!/usr/bin/env bash
# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
set -euo pipefail

export PYTHONDONTWRITEBYTECODE=1

BASE="PROJECT_DIR"
VENV_PY="${BASE}/venv/bin/python"
APP="${BASE}/app/clock.py"
LOGDIR="${BASE}/log"
LOG="${LOGDIR}/clock.log"
LOCK="/tmp/deskclock.lock"

mkdir -p "${LOGDIR}"

exec 9>"${LOCK}"
if ! flock -n 9; then
  exit 0
fi

exec >>"${LOG}" 2>&1

echo "===== deskclock start $(date '+%F %T') ====="
echo "USER=$(id -un) UID=$(id -u) GID=$(id -g)"
echo "XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-}"
echo "-------------------------------------------"

#if [ -f "$HOME/.profile" ]; then
#  source "$HOME/.profile"
#fi

#export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
#export XDG_SESSION_TYPE=wayland
#export XDG_CURRENT_DESKTOP=labwc
#export WLR_BACKENDS=drm
#export SDL_VIDEODRIVER=wayland
#unset DISPLAY
#unset WAYLAND_DISPLAY
#
#echo "Starting dbus-run-session + labwc "
#
#exec dbus-run-session -- labwc-pi > /tmp/deskclock-labwc.log 2>&1

# Waylandが起動するまで待機
export WAYLAND_DISPLAY=wayland-0

for i in {1..100}; do
    if [ -S "${XDG_RUNTIME_DIR}/${WAYLAND_DISPLAY}" ]; then
        break
    fi
    sleep 0.2
done

export SDL_VIDEODRIVER=wayland
unset DISPLAY

echo "Launching clock.py..."
exec "${VENV_PY}" "${APP}"
