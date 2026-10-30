#!/usr/bin/env bash
#
# KeySound - Kali Linux setup helper
#
# Installs the runtime dependencies and adds your desktop user to the `input`
# group so KeySound can read physical key events from /dev/input/event*.
#
# Usage:
#   sudo ./scripts/setup-kali.sh
#   sudo ./scripts/setup-kali.sh --skip-apt
#   sudo ./scripts/setup-kali.sh --skip-group
#
# The script never installs the application itself and never changes keyboard
# mappings.  It only installs packages and adjusts group membership.
set -euo pipefail

SKIP_APT=0
SKIP_GROUP=0
for arg in "$@"; do
    case "$arg" in
        --skip-apt) SKIP_APT=1 ;;
        --skip-group) SKIP_GROUP=1 ;;
        -h|--help)
            sed -n '2,20p' "$0"
            exit 0
            ;;
        *)
            echo "Unknown option: $arg" >&2
            exit 2
            ;;
    esac
done

if [[ "${EUID}" -ne 0 ]]; then
    echo "This script needs root for apt and usermod. Re-running with sudo..."
    exec sudo -- "$0" "$@"
fi

TARGET_USER="${SUDO_USER:-${KEYSOUND_USER:-}}"
if [[ -z "${TARGET_USER}" || "${TARGET_USER}" == "root" ]]; then
    if [[ -n "${KEYSOUND_USER:-}" ]]; then
        TARGET_USER="${KEYSOUND_USER}"
    else
        echo "Could not determine your desktop user." >&2
        echo "Run it as: sudo -u YOUR_USER ./scripts/setup-kali.sh" >&2
        echo "or:        sudo KEYSOUND_USER=YOUR_USER ./scripts/setup-kali.sh" >&2
        echo "or simply: sudo ./scripts/setup-kali.sh   (from your normal shell)" >&2
        exit 1
    fi
fi

if ! id "${TARGET_USER}" >/dev/null 2>&1; then
    echo "User '${TARGET_USER}' does not exist." >&2
    exit 1
fi

if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    echo "Detected: ${PRETTY_NAME:-unknown Linux}"
    case " ${ID:-} ${ID_LIKE:-} " in
        *kali*|*debian*|*ubuntu*) ;;
        *) echo "Warning: this helper is written for Kali/Debian; continuing anyway." ;;
    esac
fi

PACKAGES=(
    python3
    python3-gi
    python3-numpy
    gir1.2-gtk-3.0
    gir1.2-ayatanaappindicator3-0.1
    libpulse0
    libx11-6
    libxi6
    xdg-utils
)

if [[ "${SKIP_APT}" -eq 0 ]]; then
    echo
    echo "==> Installing runtime packages"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y --no-install-recommends "${PACKAGES[@]}"
else
    echo
    echo "==> Skipping apt (--skip-apt)"
fi

missing=()
for pkg in "${PACKAGES[@]}"; do
    if ! dpkg -s "${pkg}" >/dev/null 2>&1; then
        missing+=("${pkg}")
    fi
done
if ((${#missing[@]})); then
    echo
    echo "Warning: these packages are still missing: ${missing[*]}" >&2
fi

echo
echo "==> Checking keyboard device permissions"
if [[ -r /dev/input/event0 ]]; then
    echo "    /dev/input/event* is already readable."
else
    echo "    /dev/input/event* is not readable by root? Check your device tree."
fi

if [[ "${SKIP_GROUP}" -eq 0 ]]; then
    echo
    echo "==> Adding ${TARGET_USER} to the 'input' group"
    if id -nG "${TARGET_USER}" | tr ' ' '\n' | grep -qx input; then
        echo "    ${TARGET_USER} is already in the input group."
    else
        usermod -aG input "${TARGET_USER}"
        NEED_RELOGIN=1
        echo "    Added. A full log out and log back in is required."
    fi
else
    echo
    echo "==> Skipping group change (--skip-group)"
fi

if [[ "${NEED_RELOGIN:-0}" -eq 1 ]]; then
    echo
    echo "==> Log out of your desktop session and log back in (or reboot),"
    echo "    then start KeySound:  keysound"
    echo "    From this checkout:   python3 -m keysound"
fi

echo
echo "Privacy note:"
echo "  The input group grants read access to every input device, including"
echo "  keyboards. KeySound itself never logs, stores, or transmits key events,"
echo "  but only run software you trust with this membership."
echo
echo "Done. Start KeySound from the application menu or with: keysound"
