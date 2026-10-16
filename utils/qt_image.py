from __future__ import annotations

from PIL import Image
from PySide6.QtGui import QImage, QPixmap

from core.image_io import _normalize_mode


def _to_qimage_raw(img: Image.Image):
    if img.mode not in ("RGB", "RGBA"):
        img = _normalize_mode(img)
    w, h = img.size
    data = img.tobytes()
    if img.mode == "RGBA":
        qimg = QImage(data, w, h, w * 4, QImage.Format.Format_RGBA8888)
    else:
        qimg = QImage(data, w, h, w * 3, QImage.Format.Format_RGB888)
    return qimg, data


def pil_to_qimage(img: Image.Image) -> QImage:
    qimg, data = _to_qimage_raw(img)
    out = qimg.copy()  # detach from `data`
    del data
    return out


def pil_to_pixmap(img: Image.Image) -> QPixmap:
    qimg, data = _to_qimage_raw(img)
    pm = QPixmap.fromImage(qimg)
    del qimg, data
    return pm
