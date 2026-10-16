from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageEnhance, ImageFilter, ImageOps


# ── pixel operations ────────────────────────────────────────────────────────
def _split_alpha(img: Image.Image):
    if img.mode == "RGBA":
        return img.convert("RGB"), img.getchannel("A")
    return img.convert("RGB"), None


def _merge_alpha(rgb: Image.Image, alpha):
    if alpha is not None:
        rgb = rgb.copy()
        rgb.putalpha(alpha)
    return rgb


@dataclass
class Adjustments:
    brightness: int = 0
    contrast: int = 0
    saturation: int = 0
    temperature: int = 0
    hue: int = 0
    sharpness: int = 0

    def is_identity(self) -> bool:
        return not any(vars(self).values())


def _gain_lut(gain: float):
    return [max(0, min(255, int(i * gain + 0.5))) for i in range(256)]


def apply_adjustments(img: Image.Image, p: Adjustments) -> Image.Image:
    rgb, alpha = _split_alpha(img)
    if p.brightness:
        rgb = ImageEnhance.Brightness(rgb).enhance(1 + p.brightness / 100)
    if p.contrast:
        rgb = ImageEnhance.Contrast(rgb).enhance(1 + p.contrast / 100)
    if p.saturation:
        rgb = ImageEnhance.Color(rgb).enhance(1 + p.saturation / 100)
    if p.temperature:
        r, g, b = rgb.split()
        t = p.temperature / 100
        r = r.point(_gain_lut(1 + 0.30 * t))
        b = b.point(_gain_lut(1 - 0.30 * t))
        rgb = Image.merge("RGB", (r, g, b))
    if p.hue:
        h, s, v = rgb.convert("HSV").split()
        shift = int(round(p.hue / 360 * 256))
        h = h.point([(i + shift) % 256 for i in range(256)])
        rgb = Image.merge("HSV", (h, s, v)).convert("RGB")
    if p.sharpness:
        factor = 1 + p.sharpness / 100 if p.sharpness < 0 else 1 + p.sharpness / 25
        rgb = ImageEnhance.Sharpness(rgb).enhance(factor)
    return _merge_alpha(rgb, alpha)


def f_grayscale(img):
    rgb, a = _split_alpha(img)
    return _merge_alpha(ImageOps.grayscale(rgb).convert("RGB"), a)


def f_sepia(img):
    rgb, a = _split_alpha(img)
    gray = ImageOps.grayscale(rgb)
    return _merge_alpha(ImageOps.colorize(gray, "#2b1708", "#fff1d9", mid="#9a7048"), a)


def f_invert(img):
    rgb, a = _split_alpha(img)
    return _merge_alpha(ImageOps.invert(rgb), a)


def f_autocontrast(img):
    rgb, a = _split_alpha(img)
    return _merge_alpha(ImageOps.autocontrast(rgb, cutoff=0.5), a)


def f_blur(img):
    rgb, a = _split_alpha(img)
    radius = max(1.5, max(img.size) / 600)
    return _merge_alpha(rgb.filter(ImageFilter.GaussianBlur(radius)), a)


def f_sharpen(img):
    rgb, a = _split_alpha(img)
    radius = max(1.5, max(img.size) / 900)
    return _merge_alpha(rgb.filter(ImageFilter.UnsharpMask(radius=radius, percent=150, threshold=3)), a)
