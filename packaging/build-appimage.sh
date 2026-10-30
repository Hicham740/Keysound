#!/usr/bin/env bash
#
# Build a portable AppImage wrapper for KeySound.
#
# This is a "thin" AppImage: it bundles the KeySound Python code and assets but
# uses the system Python 3, PyGObject, GTK3, numpy and PulseAudio.  On Kali,
# install those with scripts/setup-kali.sh.  A fully self-contained AppImage
# would need to bundle the GTK typelibs and Python runtime, which is much larger
# and distro-sensitive; the .deb is the recommended package.
#
# Requires appimagetool in PATH (or set APPIMAGETOOL=/path/to/appimagetool).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(python3 -c "import sys; sys.path.insert(0, '${ROOT}'); from keysound.paths import VERSION; print(VERSION)")"
OUT="${ROOT}/dist"
APPDIR="${OUT}/KeySound.AppDir"

APPIMAGETOOL="${APPIMAGETOOL:-$(command -v appimagetool || true)}"
if [[ -z "${APPIMAGETOOL}" ]]; then
    cat >&2 <<'MSG'
appimagetool was not found.

Install it from https://github.com/AppImage/AppImageKit/releases and either put
it in PATH or run:

    APPIMAGETOOL=/path/to/appimagetool ./packaging/build-appimage.sh

The Debian package can be built without appimagetool:
    ./packaging/build-deb.sh
MSG
    exit 1
fi

rm -rf "${APPDIR}"
install -d "${APPDIR}/usr/bin" "${APPDIR}/usr/lib/keysound" "${APPDIR}/usr/share/keysound"
cp -a "${ROOT}/keysound" "${APPDIR}/usr/lib/keysound/"
cp -a "${ROOT}/run.py" "${APPDIR}/usr/lib/keysound/run.py"
cp -a "${ROOT}/scripts/setup-kali.sh" "${APPDIR}/usr/share/keysound/setup-kali.sh"
find "${APPDIR}/usr/lib/keysound" -type d -name __pycache__ -prune -exec rm -rf {} +
find "${APPDIR}/usr/lib/keysound" -type f -name '*.pyc' -delete

cp "${ROOT}/packaging/keysound.desktop" "${APPDIR}/keysound.desktop"
cp "${ROOT}/keysound/assets/icons/keysound-256.png" "${APPDIR}/keysound.png"
cp "${ROOT}/keysound/assets/icons/keysound-256.png" "${APPDIR}/.DirIcon"

cat > "${APPDIR}/AppRun" <<'APPRUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec python3 "$HERE/usr/lib/keysound/run.py" "$@"
APPRUN
chmod 0755 "${APPDIR}/AppRun"

install -d "${OUT}"
TARGET="${OUT}/KeySound-${VERSION}-x86_64.AppImage"
ARCH=x86_64 "${APPIMAGETOOL}" "${APPDIR}" "${TARGET}"
echo "Built: ${TARGET}"
