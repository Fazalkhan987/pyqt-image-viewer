#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lumina - a fast image viewer and editor for Ubuntu (and other Linux desktops).

Run:      python3 lumina.py [image-or-folder ...]
Requires: PySide6 and Pillow   (see requirements.txt / install.sh)

Highlights
  * Folder browsing with a thumbnail strip, keyboard navigation, drag & drop
  * JPEG, PNG, WebP, GIF, BMP, TIFF
  * Zoom / fit / 100 % / rotate / flip / full-screen / slideshow
  * Crop (with aspect presets), resize, brightness, contrast, saturation,
    temperature, hue, sharpness, filters
  * Unlimited-ish undo/redo (memory-bounded), live previews
  * Save As, or overwrite the original (always with confirmation)
  * Image details dialog (file info, EXIF, GPS)
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps, UnidentifiedImageError  # noqa: F401
    from PIL.ExifTags import TAGS  # noqa: F401
except ImportError:  # pragma: no cover
    sys.stderr.write("Lumina needs Pillow.  Install it with:  pip install Pillow\n")
    sys.exit(1)

try:
    from PySide6.QtCore import QSettings, QTimer
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication
except ImportError:  # pragma: no cover
    sys.stderr.write("Lumina needs PySide6.  Install it with:  pip install PySide6\n")
    sys.exit(1)

from core.constants import APP_NAME, VERSION
from ui.main_window import MainWindow
from ui.theme import apply_theme
from utils.helpers import list_images


def main(argv: list[str]) -> int:
    if any(a in ("-h", "--help") for a in argv[1:]):
        print(f"{APP_NAME} {VERSION}\nUsage: lumina [IMAGE_OR_FOLDER ...]")
        return 0
    if any(a == "--version" for a in argv[1:]):
        print(f"{APP_NAME} {VERSION}")
        return 0
    app = QApplication(argv)
    app.setOrganizationName("Lumina")
    app.setApplicationName("lumina")
    app.setApplicationDisplayName(APP_NAME)
    QGuiApplication.setDesktopFileName("lumina")
    app.setStyle("Fusion")
    apply_theme(app, str(QSettings().value("theme", "system")))

    win = MainWindow()
    win.show()
    paths = [a for a in argv[1:] if not a.startswith("-")]
    if paths:
        target = os.path.abspath(paths[0])
        if os.path.isdir(target):
            files = list_images(target)
            target = files[0] if files else target
        QTimer.singleShot(0, lambda: win.open_path(target, explicit=True))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
