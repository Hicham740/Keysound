#!/usr/bin/env bash
#
# Build a Debian package for KeySound.
#
# Output: dist/keysound_<version>_all.deb
#
# The package installs the application under /usr/lib/keysound and a small
# launcher at /usr/bin/keysound.  It does not add the user to the input group;
# run scripts/setup-kali.sh (also installed to /usr/share/keysound) for that.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(python3 -c "import sys; sys.path.insert(0, '${ROOT}'); from keysound.paths import VERSION; print(VERSION)")"
OUT="${ROOT}/dist"
STAGE="${OUT}/build/keysound-${VERSION}"

echo "==> KeySound ${VERSION}"
echo "==> Staging in ${STAGE}"
rm -rf "${STAGE}"
install -d "${STAGE}/DEBIAN"
install -d "${STAGE}/usr/bin"
install -d "${STAGE}/usr/lib/keysound"
install -d "${STAGE}/usr/share/applications"
install -d "${STAGE}/usr/share/keysound"
install -d "${STAGE}/usr/share/doc/keysound"

# Application code and generated assets.
cp -a "${ROOT}/keysound" "${STAGE}/usr/lib/keysound/"
cp -a "${ROOT}/run.py" "${STAGE}/usr/lib/keysound/run.py"
find "${STAGE}/usr/lib/keysound" -type d -name __pycache__ -prune -exec rm -rf {} +
find "${STAGE}/usr/lib/keysound" -type f -name '*.pyc' -delete

# Launcher.
cat > "${STAGE}/usr/bin/keysound" <<'WRAPPER'
#!/bin/sh
exec python3 /usr/lib/keysound/run.py "$@"
WRAPPER
chmod 0755 "${STAGE}/usr/bin/keysound"

# Desktop entry and icons.
install -Dm644 "${ROOT}/packaging/keysound.desktop" \
    "${STAGE}/usr/share/applications/keysound.desktop"
for size in 16 24 32 48 64 128 256; do
    install -Dm644 "${ROOT}/keysound/assets/icons/keysound-${size}.png" \
        "${STAGE}/usr/share/icons/hicolor/${size}x${size}/apps/keysound.png"
done
install -Dm644 "${ROOT}/keysound/assets/icons/keysound.svg" \
    "${STAGE}/usr/share/icons/hicolor/scalable/apps/keysound.svg"

# Setup helper, documentation, licence.
install -Dm755 "${ROOT}/scripts/setup-kali.sh" \
    "${STAGE}/usr/share/keysound/setup-kali.sh"
install -Dm644 "${ROOT}/README.md" "${STAGE}/usr/share/doc/keysound/README.md"
install -Dm644 "${ROOT}/keysound/assets/sounds/CREDITS.md" \
    "${STAGE}/usr/share/doc/keysound/CREDITS.md"
if [[ -f "${ROOT}/IMPLEMENTATION_REPORT.txt" ]]; then
    install -Dm644 "${ROOT}/IMPLEMENTATION_REPORT.txt" \
        "${STAGE}/usr/share/doc/keysound/IMPLEMENTATION_REPORT.txt"
fi
install -Dm644 "${ROOT}/packaging/copyright" \
    "${STAGE}/usr/share/doc/keysound/copyright"

INSTALLED_SIZE="$(du -sk "${STAGE}/usr" | cut -f1)"
cat > "${STAGE}/DEBIAN/control" <<CONTROL
Package: keysound
Version: ${VERSION}
Section: sound
Priority: optional
Architecture: all
Installed-Size: ${INSTALLED_SIZE}
Depends: python3 (>= 3.10), python3-gi, python3-numpy, gir1.2-gtk-3.0, gir1.2-ayatanaappindicator3-0.1, libpulse0, libx11-6, libxi6, xdg-utils
Recommends: pipewire-pulse | pulseaudio
Maintainer: KeySound Contributors <keysound@localhost>
Homepage: https://shotgunkeyboard.com
Description: per-key keyboard sounds for Kali Linux
 KeySound listens to physical key events system-wide and plays a
 different, user-assigned sound for each key.  It includes a visual
 keyboard editor, per-key and per-group volume/pitch/variant controls,
 12-voice polyphony, profiles, a tray indicator, autostart, and a global
 mute hotkey.
 .
 Key events are mapped to sounds in memory and immediately discarded.
 No keystrokes are logged, stored, or transmitted.
CONTROL

cat > "${STAGE}/DEBIAN/postinst" <<'POSTINST'
#!/bin/sh
set -e
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications >/dev/null 2>&1 || true
fi
cat <<'MSG'

KeySound is installed.  Start it from the application menu or with:

    keysound

For direct evdev access (recommended; required on Wayland), run:

    sudo /usr/share/keysound/setup-kali.sh

then log out and back in.  Without that step on X11, KeySound uses the
XInput2 fallback automatically.

MSG
exit 0
POSTINST
chmod 0755 "${STAGE}/DEBIAN/postinst"

cat > "${STAGE}/DEBIAN/prerm" <<'PRERM'
#!/bin/sh
set -e
exit 0
PRERM
chmod 0755 "${STAGE}/DEBIAN/prerm"

# Debian packages expect configuration files to be listed here when relevant.
# KeySound keeps settings in the user's home directory, so there are none.

install -d "${OUT}"
DEB="${OUT}/keysound_${VERSION}_all.deb"
dpkg-deb --build --root-owner-group "${STAGE}" "${DEB}"

if command -v desktop-file-validate >/dev/null 2>&1; then
    desktop-file-validate "${STAGE}/usr/share/applications/keysound.desktop" || true
fi

echo
echo "Built: ${DEB}"
echo "Inspect: dpkg-deb -I '${DEB}'"
echo "Install: sudo apt-get install -y '${DEB}'"
