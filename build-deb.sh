#!/usr/bin/env bash
# Build a local Debian package:
#   ./build-deb.sh
#   ./build-deb.sh 1.0.1
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="${1:-1.0.0}"
PACKAGE="lumina"
BUILD_ROOT="$(mktemp -d)"
PKG_ROOT="$BUILD_ROOT/$PACKAGE"
OUTPUT="$SRC/${PACKAGE}.deb"

cleanup() {
  rm -rf "$BUILD_ROOT"
}
trap cleanup EXIT

install -d "$PKG_ROOT/DEBIAN" \
  "$PKG_ROOT/usr/lib/lumina" \
  "$PKG_ROOT/usr/bin" \
  "$PKG_ROOT/usr/share/applications" \
  "$PKG_ROOT/usr/share/icons/hicolor/scalable/apps"

cat > "$PKG_ROOT/DEBIAN/control" <<CONTROL
Package: lumina
Version: $VERSION
Section: graphics
Priority: optional
Architecture: all
Maintainer: Lumina contributors
Depends: python3, python3-pil, python3-pyside6.qtcore, python3-pyside6.qtgui, python3-pyside6.qtwidgets
Description: Image viewer and editor
 Lumina is a Qt image viewer and editor with browsing, editing,
 metadata inspection, and desktop background support.
CONTROL

install -m 644 "$SRC/lumina.py" "$PKG_ROOT/usr/lib/lumina/lumina.py"
install -m 644 "$SRC/lumina.svg" "$PKG_ROOT/usr/share/icons/hicolor/scalable/apps/lumina.svg"
for package in core ui utils; do
  cp -a "$SRC/$package" "$PKG_ROOT/usr/lib/lumina/$package"
  find "$PKG_ROOT/usr/lib/lumina/$package" -type d -name __pycache__ -prune -exec rm -rf {} +
done

cat > "$PKG_ROOT/usr/bin/lumina" <<'LAUNCHER'
#!/bin/sh
exec /usr/bin/python3 /usr/lib/lumina/lumina.py "$@"
LAUNCHER
chmod 755 "$PKG_ROOT/usr/bin/lumina"

cat > "$PKG_ROOT/usr/share/applications/lumina.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Lumina
GenericName=Image Viewer and Editor
Comment=View, browse and edit your pictures
Exec=/usr/bin/lumina %F
Icon=lumina
Terminal=false
Categories=Graphics;Viewer;2DGraphics;RasterGraphics;
MimeType=image/jpeg;image/png;image/webp;image/gif;image/bmp;image/tiff;
StartupWMClass=lumina
Keywords=image;photo;picture;viewer;editor;
DESKTOP

rm -f "$OUTPUT"
dpkg-deb --build --root-owner-group "$PKG_ROOT" "$OUTPUT" >/dev/null
echo "Built: $OUTPUT"
echo "Install: sudo apt install $OUTPUT"
