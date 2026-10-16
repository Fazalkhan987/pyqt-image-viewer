from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QPushButton, QSlider, QVBoxLayout, QWidget)

from core.adjustments import Adjustments


class ResetSlider(QSlider):
    """Slider that resets to 0 on double-click."""
    def mouseDoubleClickEvent(self, e):
        self.setValue(0)


class SliderRow(QWidget):
    valueChanged = Signal(int)

    def __init__(self, title: str, minimum=-100, maximum=100, parent=None):
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setVerticalSpacing(0)
        self.title = QLabel(title)
        self.value_label = QLabel("0")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.value_label.setMinimumWidth(40)
        self.slider = ResetSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(minimum, maximum)
        self.slider.setValue(0)
        self.slider.setAccessibleName(title)
        self.slider.setToolTip(f"{title} — double-click to reset")
        self.title.setBuddy(self.slider)
        grid.addWidget(self.title, 0, 0)
        grid.addWidget(self.value_label, 0, 1)
        grid.addWidget(self.slider, 1, 0, 1, 2)
        self.slider.valueChanged.connect(self._changed)

    def _changed(self, v: int):
        self.value_label.setText(f"{v:+d}" if v else "0")
        self.valueChanged.emit(v)

    def value(self) -> int:
        return self.slider.value()

    def set_value(self, v: int):
        self.slider.setValue(v)


class AdjustPanel(QGroupBox):
    changed = Signal()
    applyClicked = Signal()

    def __init__(self, parent=None):
        super().__init__("Adjust", parent)
        lay = QVBoxLayout(self)
        self.rows = {
            "brightness": SliderRow("Brightness"),
            "contrast": SliderRow("Contrast"),
            "saturation": SliderRow("Saturation"),
            "temperature": SliderRow("Temperature (cool ↔ warm)"),
            "hue": SliderRow("Hue shift", -180, 180),
            "sharpness": SliderRow("Sharpness"),
        }
        for row in self.rows.values():
            lay.addWidget(row)
            row.valueChanged.connect(self._on_change)
        buttons = QHBoxLayout()
        self.btn_reset = QPushButton("Reset")
        self.btn_apply = QPushButton("Apply")
        self.btn_apply.setDefault(False)
        self.btn_apply.setToolTip("Commit these adjustments to the image (adds an undo step)")
        self.btn_reset.clicked.connect(lambda: self.reset())
        self.btn_apply.clicked.connect(self.applyClicked.emit)
        buttons.addWidget(self.btn_reset)
        buttons.addWidget(self.btn_apply)
        lay.addLayout(buttons)
        self._on_change(emit=False)

    def params(self) -> Adjustments:
        return Adjustments(**{k: r.value() for k, r in self.rows.items()})

    def _on_change(self, *_, emit=True):
        active = not self.params().is_identity()
        self.btn_apply.setEnabled(active)
        self.btn_reset.setEnabled(active)
        if emit:
            self.changed.emit()

    def reset(self, silent=False):
        for r in self.rows.values():
            r.slider.blockSignals(True)
            r.set_value(0)
            r.value_label.setText("0")
            r.slider.blockSignals(False)
        self._on_change(emit=not silent)

