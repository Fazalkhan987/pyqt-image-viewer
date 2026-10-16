from __future__ import annotations

from PIL import Image, ImageOps
from PySide6.QtCore import QObject, QRunnable, Signal
from PySide6.QtGui import QImage

from core.constants import RS
from core.image_io import _normalize_mode
from utils.qt_image import pil_to_qimage


class ThumbSignals(QObject):
    loaded = Signal(int, str, QImage)


class ThumbTask(QRunnable):
    def __init__(self, gen: int, path: str, size: int, signals: ThumbSignals):
        super().__init__()
        self.gen, self.path, self.size, self.signals = gen, path, size, signals

    def run(self):
        qimg = QImage()
        try:
            with Image.open(self.path) as im:
                try:
                    im.draft("RGB", (self.size * 2, self.size * 2))  # fast JPEG decode
                except Exception:
                    pass
                im.load()
                try:
                    im = ImageOps.exif_transpose(im)
                except Exception:
                    pass
                im.thumbnail((self.size, self.size), RS.BILINEAR)
                qimg = pil_to_qimage(_normalize_mode(im))
        except Exception:
            qimg = QImage()
        self.signals.loaded.emit(self.gen, self.path, qimg)
