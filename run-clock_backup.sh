#!/usr/bin/env bash
set -euo pipefail

# ---- paths ----
BASE="PROJECT_DIR"
VENV_PY="${BASE}/venv/bin/python"
APP="${BASE}/app/clock.py"
LOGDIR="${BASE}/log"
LOG="${LOGDIR}/clock.log"
LOCK="/tmp/deskclock.lock"

mkdir -p "${LOGDIR}"

# ---- single instance ----
exec 9>"${LOCK}"
if ! flock -n 9; then
  exit 0
fi

# ---- logging (append) ----
exec >>"${LOG}" 2>&1
echo "===== deskclock start $(date '+%F %T') ====="
echo "USER=$(id -un) UID=$(id -u) GID=$(id -g)"
echo "PWD=$(pwd)"
echo "DISPLAY=${DISPLAY:-}"
echo "WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-}"
echo "XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-}"
echo "PY=${VENV_PY}"
echo "-------------------------------------------"

# ---- environment (keep clock.py unchanged) ----
# SwitchBot env vars etc. (you already use ~/.profile)
# NOTE: systemd user service does NOT always load ~/.profile automatically.
# We explicitly source it here to match your working manual method.
if [ -f "$HOME/.profile" ]; then
  # shellcheck disable=SC1091
  source "$HOME/.profile"
fi

# ---- wait for GUI session readiness (Wayland preferred) ----
# WAYLAND_DISPLAY が空でも、通常は wayland-0 が来るのでそれも候補にする
if [ -z "${WAYLAND_DISPLAY:-}" ]; then
  export WAYLAND_DISPLAY="wayland-0"
fi

# Wayland socket を最大10秒待つ（起動を急がない）
for i in {1..50}; do
  if [ -n "${XDG_RUNTIME_DIR:-}" ] && [ -S "${XDG_RUNTIME_DIR}/${WAYLAND_DISPLAY}" ]; then
    break
  fi
  sleep 0.2
done

# ---- choose SDL backend ----
# Wayland が使えるなら Wayland を強制し、X11 を使わせない（XIO回避）
if [ -n "${XDG_RUNTIME_DIR:-}" ] && [ -S "${XDG_RUNTIME_DIR}/${WAYLAND_DISPLAY}" ]; then
  export SDL_VIDEODRIVER="wayland"
  unset DISPLAY
  echo "SDL_VIDEODRIVER=wayland (DISPLAY unset)"
else
  # Wayland が無いなら X11 に倒す
  export SDL_VIDEODRIVER="x11"
  echo "SDL_VIDEODRIVER=x11 (DISPLAY=${DISPLAY:-unset})"
fi

# ---- soft guard: if the session isn't ready, wait a bit (avoid "too fast startup" issues) ----
# 例: GUI直後にWAYLAND_DISPLAYがまだ無い等を避ける
for i in {1..20}; do
  if [ -n "${XDG_RUNTIME_DIR:-}" ] && [ -S "${XDG_RUNTIME_DIR}/${WAYLAND_DISPLAY:-}" ]; then
    break
  fi
  sleep 0.2
done

# ---- run ----
echo "Launching clock.py..."
exec "${VENV_PY}" "${APP}"

