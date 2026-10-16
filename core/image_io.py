from __future__ import annotations

import os
from dataclasses import dataclass

from PIL import Image, ImageOps


@dataclass
class ImageMeta:
    format: str
    mode: str
    frames: int
    animated: bool
    dpi: tuple | None
    has_icc: bool
    exif: object | None
    info: dict
    orig_size: tuple


@dataclass
class Loaded:
    image: Image.Image
    meta: ImageMeta


def _normalize_mode(img: Image.Image) -> Image.Image:
    """Bring any Pillow mode to plain RGB / RGBA for editing and display."""
    if img.mode in ("RGB", "RGBA"):
        return img
    if img.mode in ("I;16", "I;16L", "I;16B", "I;16N", "I", "F"):
        try:
            return img.point(lambda i: i * (1 / 256)).convert("L").convert("RGB")
        except Exception:
            return img.convert("RGB")
    has_alpha = ("A" in img.getbands()) or (img.mode == "P" and "transparency" in img.info) \
        or img.mode == "PA"
    return img.convert("RGBA" if has_alpha else "RGB")


def _copy_exif(im: Image.Image):
    try:
        ex = im.getexif()
        if not ex:
            return None
        copy = Image.Exif()
        copy.load(ex.tobytes())
        if 0x0112 in copy:      # orientation has already been applied to the pixels
            copy[0x0112] = 1
        return copy
    except Exception:
        return None


def load_image(path: str) -> Loaded:
    os.stat(path)  # raises FileNotFoundError / PermissionError early
    if os.path.isdir(path):
        raise IsADirectoryError(path)
    im = Image.open(path)
    try:
        fmt = im.format or ""
        mode = im.mode
        frames = int(getattr(im, "n_frames", 1) or 1)
        animated = bool(getattr(im, "is_animated", False))
        dpi = im.info.get("dpi")
        try:
            dpi = tuple(float(x) for x in dpi) if dpi else None
        except Exception:
            dpi = None
        has_icc = bool(im.info.get("icc_profile"))
        exif = _copy_exif(im)
        info = dict(im.info)
        orig_size = im.size
        im.load()
        try:
            img = ImageOps.exif_transpose(im)
        except Exception:
            img = None
        if img is None or img is im:
            img = im.copy()
        img = _normalize_mode(img)
    finally:
        im.close()
    return Loaded(img, ImageMeta(fmt, mode, frames, animated, dpi, has_icc, exif, info, orig_size))


def save_image_file(img: Image.Image, path: str, fmt: str, quality: int, meta: ImageMeta | None):
    params: dict = {}
    out = img
    if fmt == "JPEG":
        if out.mode == "RGBA":      # JPEG has no transparency: flatten onto white
            bg = Image.new("RGB", out.size, (255, 255, 255))
            bg.paste(out, mask=out.getchannel("A"))
            out = bg
        elif out.mode != "RGB":
            out = out.convert("RGB")
        params.update(quality=quality, optimize=True)
    elif fmt == "WEBP":
        params.update(quality=quality, method=4)
    elif fmt == "PNG":
        params.update(compress_level=6)
    elif fmt == "TIFF":
        params.update(compression="tiff_lzw")
    if meta and meta.dpi and fmt in ("JPEG", "PNG", "TIFF"):
        params["dpi"] = meta.dpi

    attempts = []
    if meta and meta.exif is not None and fmt in ("JPEG", "WEBP", "PNG"):
        attempts.append(dict(params, exif=meta.exif))
    attempts.append(params)
    attempts.append({"quality": quality} if fmt in ("JPEG", "WEBP") else {})
    last = None
    for p in attempts:
        try:
            out.save(path, format=fmt, **p)
            return
        except Exception as exc:  # try a simpler set of options
            last = exc
    raise last  # type: ignore[misc]
