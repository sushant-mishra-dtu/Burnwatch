#!/usr/bin/env bash
# Run a BurnWatch device script on the PYNQ as root, inside the PYNQ venv, from the repo root.
#   bash device/run.sh device/hdmi_check.py [args...]
# PYNQ >= 2.7 keeps pynq in a venv (/etc/profile.d/pynq_venv.sh -> /usr/local/share/pynq-venv);
# older images install it into the system python3, which is used as the fallback.
set -euo pipefail
if [ $# -lt 1 ]; then echo "usage: bash device/run.sh <script.py> [args...]" >&2; exit 2; fi
if [ "$(id -u)" -ne 0 ]; then exec sudo bash "$0" "$@"; fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

set +eu  # the profile scripts aren't written for strict mode
[ -f /etc/profile.d/xrt_setup.sh ] && source /etc/profile.d/xrt_setup.sh
if [ -f /etc/profile.d/pynq_venv.sh ]; then
    source /etc/profile.d/pynq_venv.sh
elif [ -f /usr/local/share/pynq-venv/bin/activate ]; then
    source /usr/local/share/pynq-venv/bin/activate
else
    echo "run.sh: no PYNQ venv found; using $(command -v python3)" >&2
fi
set -eu

export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec python3 "$@"
