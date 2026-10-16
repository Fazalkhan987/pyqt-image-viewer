from __future__ import annotations

import os
import re

from PIL import Image, UnidentifiedImageError

from core.constants import SUPPORTED_EXTS


def natural_key(name: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def list_images(folder: str) -> list[str]:
    try:
        with os.scandir(folder) as it:
            files = [e.path for e in it
                     if e.is_file() and not e.name.startswith(".")
                     and e.name.lower().endswith(SUPPORTED_EXTS)]
    except OSError:
        return []
    files.sort(key=lambda p: natural_key(os.path.basename(p)))
    return files


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} B"


def describe_error(path: str, exc: Exception) -> tuple[str, str]:
    """Turn an exception into a (title, friendly explanation) pair."""
    name = os.path.basename(path)
    if isinstance(exc, FileNotFoundError):
        return ("File not found",
                f"“{name}” no longer exists. It may have been moved, renamed or deleted.")
    if isinstance(exc, PermissionError):
        return ("Permission denied", f"You don't have permission to read “{name}”.")
    if isinstance(exc, IsADirectoryError):
        return ("That's a folder", f"“{name}” is a folder, not an image file.")
    if isinstance(exc, Image.DecompressionBombError):
        return ("Image is too large",
                f"“{name}” has an extraordinary number of pixels, so Lumina refused to open it "
                "to protect your computer.")
    if isinstance(exc, UnidentifiedImageError):
        return ("Unsupported or damaged image",
                f"“{name}” isn't a supported image, or the file is damaged.\n\n"
                "Supported formats: JPEG, PNG, WebP, GIF, BMP and TIFF.")
    if isinstance(exc, MemoryError):
        return ("Not enough memory", f"There isn't enough free memory to open “{name}”.")
    if isinstance(exc, OSError):
        return ("Couldn't read the image",
                f"“{name}” could not be read completely. It may be truncated or corrupted.\n\n"
                f"Technical detail: {exc}")
    return ("Unexpected error", f"{type(exc).__name__}: {exc}")
