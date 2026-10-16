from __future__ import annotations

from PIL import Image

from core.image_io import ImageMeta, Loaded


class Document:
    MAX_STEPS = 40
    BUDGET_BYTES = 900 * 1024 * 1024

    def __init__(self):
        self.clear()

    def clear(self):
        self.image: Image.Image | None = None
        self.meta: ImageMeta | None = None
        self.path: str | None = None
        self._undo: list[tuple[str, Image.Image]] = []
        self._redo: list[tuple[str, Image.Image]] = []
        self._clean = None

    def load(self, path: str, loaded: Loaded):
        self.clear()
        self.image, self.meta, self.path = loaded.image, loaded.meta, path
        self._clean = self.image

    @property
    def dirty(self) -> bool:
        return self.image is not None and self.image is not self._clean

    @property
    def can_undo(self): return bool(self._undo)

    @property
    def can_redo(self): return bool(self._redo)

    @property
    def undo_label(self): return self._undo[-1][0] if self._undo else ""

    @property
    def redo_label(self): return self._redo[-1][0] if self._redo else ""

    @property
    def undo_depth(self): return len(self._undo)

    def commit(self, label: str, new_image: Image.Image):
        self._undo.append((label, self.image))
        self._redo.clear()
        self.image = new_image
        self._trim()

    def _trim(self):
        def cost(i): return i.width * i.height * len(i.getbands())
        total = sum(cost(i) for _, i in self._undo)
        while self._undo and (len(self._undo) > self.MAX_STEPS or total > self.BUDGET_BYTES):
            _, old = self._undo.pop(0)
            total -= cost(old)

    def undo(self):
        if not self._undo:
            return None
        label, prev = self._undo.pop()
        self._redo.append((label, self.image))
        self.image = prev
        return label

    def redo(self):
        if not self._redo:
            return None
        label, nxt = self._redo.pop()
        self._undo.append((label, self.image))
        self.image = nxt
        return label

    def mark_saved(self, path: str, fmt: str):
        self._clean = self.image
        self.path = path
        if self.meta:
            self.meta.format = fmt
            self.meta.animated = False
            self.meta.frames = 1
