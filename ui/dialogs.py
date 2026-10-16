from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QGuiApplication, QPalette
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QFormLayout, QHeaderView,
                               QLabel, QSpinBox, QTableWidget, QTableWidgetItem,
                               QVBoxLayout)

from core.constants import RS


class ResizeDialog(QDialog):
    METHODS = [("Lanczos (best quality)", int(RS.LANCZOS)), ("Bicubic", int(RS.BICUBIC)),
               ("Bilinear", int(RS.BILINEAR)), ("Nearest (pixel art)", int(RS.NEAREST))]

    def __init__(self, w: int, h: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Resize Image")
        self._ow, self._oh, self._busy = w, h, False
        form = QFormLayout(self)
        self.sw = QSpinBox(); self.sw.setRange(1, 30000); self.sw.setValue(w); self.sw.setSuffix(" px")
        self.sh = QSpinBox(); self.sh.setRange(1, 30000); self.sh.setValue(h); self.sh.setSuffix(" px")
        self.sp = QSpinBox(); self.sp.setRange(1, 800); self.sp.setValue(100); self.sp.setSuffix(" %")
        self.lock = QCheckBox("Keep aspect ratio"); self.lock.setChecked(True)
        self.method = QComboBox()
        for label, val in self.METHODS:
            self.method.addItem(label, val)
        self.sw.setAccessibleName("Width in pixels")
        self.sh.setAccessibleName("Height in pixels")
        self.sp.setAccessibleName("Scale in percent")
        form.addRow(QLabel(f"Current size: {w} × {h} px"))
        form.addRow("&Width:", self.sw)
        form.addRow("&Height:", self.sh)
        form.addRow("&Scale:", self.sp)
        form.addRow(self.lock)
        form.addRow("&Resampling:", self.method)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        box.button(QDialogButtonBox.StandardButton.Ok).setText("Resize")
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        form.addRow(box)
        self.sw.valueChanged.connect(self._w_changed)
        self.sh.valueChanged.connect(self._h_changed)
        self.sp.valueChanged.connect(self._p_changed)

    def _set(self, w=None, h=None, p=None):
        self._busy = True
        if w is not None: self.sw.setValue(max(1, w))
        if h is not None: self.sh.setValue(max(1, h))
        if p is not None: self.sp.setValue(max(1, min(800, p)))
        self._busy = False

    def _w_changed(self, v):
        if self._busy: return
        h = round(v * self._oh / self._ow) if self.lock.isChecked() else None
        self._set(h=h, p=round(v * 100 / self._ow))

    def _h_changed(self, v):
        if self._busy: return
        w = round(v * self._ow / self._oh) if self.lock.isChecked() else None
        self._set(w=w, p=round(v * 100 / self._oh))

    def _p_changed(self, v):
        if self._busy: return
        self._set(w=round(self._ow * v / 100), h=round(self._oh * v / 100))

    def values(self):
        return self.sw.value(), self.sh.value(), int(self.method.currentData())


class DetailsDialog(QDialog):
    def __init__(self, sections, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Image Details")
        self.resize(560, 620)
        lay = QVBoxLayout(self)
        self.table = QTableWidget(0, 2)
        self.table.horizontalHeader().setVisible(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setShowGrid(False)
        self.table.setWordWrap(True)
        self.table.setAccessibleName("Image details")
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 190)
        lay.addWidget(self.table)
        self._text = []
        for title, rows in sections:
            if not rows:
                continue
            r = self.table.rowCount()
            self.table.insertRow(r)
            head = QTableWidgetItem(title)
            f = head.font(); f.setBold(True); head.setFont(f)
            head.setBackground(QBrush(self.palette().color(QPalette.ColorRole.AlternateBase)))
            head.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(r, 0, head)
            self.table.setSpan(r, 0, 1, 2)
            self._text.append(f"[{title}]")
            for k, v in rows:
                r = self.table.rowCount()
                self.table.insertRow(r)
                self.table.setItem(r, 0, QTableWidgetItem(k))
                self.table.setItem(r, 1, QTableWidgetItem(str(v)))
                self._text.append(f"{k}: {v}")
            self._text.append("")
        self.table.resizeRowsToContents()
        buttons = QDialogButtonBox()
        copy = buttons.addButton("Copy to Clipboard", QDialogButtonBox.ButtonRole.ActionRole)
        close = buttons.addButton(QDialogButtonBox.StandardButton.Close)
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText("\n".join(self._text)))
        close.clicked.connect(self.accept)
        lay.addWidget(buttons)
