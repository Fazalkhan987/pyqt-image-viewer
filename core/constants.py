from __future__ import annotations

from PIL import Image

# Pillow renamed its enums in 9.1; support both.
RS = getattr(Image, "Resampling", Image)
TR = getattr(Image, "Transpose", Image)

APP_NAME = "Lumina"
VERSION = "1.0.0"
ORANGE = "#E95420"  # Ubuntu orange

EXT_TO_FORMAT = {
    ".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP",
    ".gif": "GIF", ".bmp": "BMP", ".tif": "TIFF", ".tiff": "TIFF",
}
SUPPORTED_EXTS = tuple(EXT_TO_FORMAT)
_PATTERNS = " ".join(f"*{e} *{e.upper()}" for e in SUPPORTED_EXTS)
OPEN_FILTER = f"Images ({_PATTERNS});;All files (*)"
SAVE_FILTERS = [
    ("PNG image (*.png)", ".png"),
    ("JPEG image (*.jpg *.jpeg)", ".jpg"),
    ("WebP image (*.webp)", ".webp"),
    ("TIFF image (*.tif *.tiff)", ".tif"),
    ("BMP image (*.bmp)", ".bmp"),
    ("GIF image (*.gif)", ".gif"),
]
MAX_RESIZE_PIXELS = 150_000_000
EXIF_IFD, GPS_IFD = 0x8769, 0x8825

MODE_NAMES = {"RGB": "RGB (24-bit colour)", "RGBA": "RGBA (colour + transparency)",
              "L": "Grayscale (8-bit)", "LA": "Grayscale + transparency", "P": "Indexed palette",
              "1": "Black & white (1-bit)", "CMYK": "CMYK (print)", "I;16": "Grayscale (16-bit)",
              "PA": "Palette + transparency"}
