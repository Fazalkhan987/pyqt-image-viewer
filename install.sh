#!/usr/bin/env bash
# Installs Lumina for the current user on Ubuntu (22.04 / 24.04 or newer).
#   ./install.sh              install
#   ./install.sh --uninstall  remove
set -euo pipefail

APP_DIR="$HOME/.local/share/lumina"
BIN="$HOME/.local/bin/lumina"
DESKTOP="$HOME/.local/share/applications/lumina.desktop"
ICON="$HOME/.local/share/icons/hicolor/scalable/apps/lumina.svg"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" == "--uninstall" ]]; then
  rm -rf "$APP_DIR" "$BIN" "$DESKTOP" "$ICON"
  command -v update-desktop-database >/dev/null && update-desktop-database "$HOME/.local/share/applications" || true
  echo "Lumina removed."
  exit 0
fi

echo "==> Installing system libraries Qt needs (sudo password may be requested)"
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip \
  libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0 \
  libxcb-shape0 libxcb-xinerama0 libxkbcommon-x11-0 libegl1 libgl1

echo "==> Creating Python environment in $APP_DIR"
mkdir -p "$APP_DIR" "$(dirname "$BIN")" "$(dirname "$DESKTOP")" "$(dirname "$ICON")"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip >/dev/null
"$APP_DIR/venv/bin/pip" install -r "$SRC/requirements.txt"

echo "==> Installing application files"
install -m 644 "$SRC/lumina.py"  "$APP_DIR/lumina.py"
install -m 644 "$SRC/lumina.svg" "$ICON"
for package in core ui utils; do
  rm -rf "$APP_DIR/$package"
  cp -a "$SRC/$package" "$APP_DIR/$package"
done

cat > "$BIN" <<LAUNCH
#!/usr/bin/env bash
exec "$APP_DIR/venv/bin/python" "$APP_DIR/lumina.py" "\$@"
LAUNCH
chmod +x "$BIN"

cat > "$DESKTOP" <<ENTRY
[Desktop Entry]
Type=Application
Name=Lumina
GenericName=Image Viewer and Editor
Comment=View, browse and edit your pictures
Exec=$BIN %F
Icon=lumina
Terminal=false
Categories=Graphics;Viewer;2DGraphics;RasterGraphics;
MimeType=image/jpeg;image/png;image/webp;image/gif;image/bmp;image/tiff;
StartupWMClass=lumina
Keywords=image;photo;picture;viewer;editor;
ENTRY

command -v update-desktop-database >/dev/null && update-desktop-database "$HOME/.local/share/applications" || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

echo
echo "Done!  Find “Lumina” in your app launcher, or run:  lumina photo.jpg"
echo "(If 'lumina' isn't found, log out and back in so ~/.local/bin is on your PATH.)"
echo "To make it the default viewer: right-click an image → Properties → Open With → Lumina."
