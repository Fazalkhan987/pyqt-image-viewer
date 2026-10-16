from __future__ import annotations

import subprocess

from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import (QColor, QGuiApplication, QIcon, QPainter, QPalette,
                           QPixmap, QPolygonF)
from PySide6.QtWidgets import QApplication

from core.constants import ORANGE


def system_prefers_dark() -> bool:
    def gs(key):
        try:
            r = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", key],
                               capture_output=True, text=True, timeout=2)
            return r.stdout.strip().lower() if r.returncode == 0 else ""
        except Exception:
            return ""
    scheme = gs("color-scheme")
    if scheme:
        return "dark" in scheme
    if "dark" in gs("gtk-theme"):
        return True
    try:
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorScheme"):
            return hints.colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        pass
    return False


def build_palette(dark: bool) -> QPalette:
    P, G = QPalette.ColorRole, QPalette.ColorGroup
    p = QPalette()
    c = QColor
    if dark:
        colors = {
            P.Window: c("#2d2d2d"), P.WindowText: c("#eeeeee"), P.Base: c("#1f1f1f"),
            P.AlternateBase: c("#353535"), P.ToolTipBase: c("#3a3a3a"), P.ToolTipText: c("#eeeeee"),
            P.Text: c("#eeeeee"), P.Button: c("#3c3c3c"), P.ButtonText: c("#eeeeee"),
            P.BrightText: c("#ffffff"), P.Link: c("#7db9ff"), P.Highlight: c(ORANGE),
            P.HighlightedText: c("#ffffff"), P.PlaceholderText: c("#8a8a8a"),
            P.Light: c(80, 80, 80), P.Midlight: c(62, 62, 62), P.Dark: c(28, 28, 28),
            P.Mid: c(45, 45, 45), P.Shadow: c(0, 0, 0),
        }
        disabled = c("#7a7a7a")
    else:
        colors = {
            P.Window: c("#f6f5f4"), P.WindowText: c("#3d3846"), P.Base: c("#ffffff"),
            P.AlternateBase: c("#f0eeed"), P.ToolTipBase: c("#ffffff"), P.ToolTipText: c("#3d3846"),
            P.Text: c("#2e2e2e"), P.Button: c("#ebe9e7"), P.ButtonText: c("#2e2e2e"),
            P.BrightText: c("#000000"), P.Link: c("#0b5fc4"), P.Highlight: c(ORANGE),
            P.HighlightedText: c("#ffffff"), P.PlaceholderText: c("#8a8a8a"),
        }
        disabled = c("#9a9996")
    for role, col in colors.items():
        p.setColor(role, col)
    for role in (P.Text, P.ButtonText, P.WindowText):
        p.setColor(G.Disabled, role, disabled)
    return p


def apply_theme(app: QApplication, mode: str):
    dark = system_prefers_dark() if mode == "system" else mode == "dark"
    app.setPalette(build_palette(dark))


def tint_icon(icon: QIcon, color: QColor) -> QIcon:
    out = QIcon()
    for size in (16, 22, 24, 32, 48):
        pm = icon.pixmap(QSize(size, size))
        if pm.isNull():
            continue
        painter = QPainter(pm)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(pm.rect(), color)
        painter.end()
        out.addPixmap(pm)
    return out


def themed_icon(names, color: QColor) -> QIcon:
    """Prefer the symbolic (monochrome) variant and recolour it for the current palette."""
    if isinstance(names, str):
        names = (names,)
    for n in names:
        sym = QIcon.fromTheme(n + "-symbolic")
        if not sym.isNull():
            return tint_icon(sym, color)
        ic = QIcon.fromTheme(n)
        if not ic.isNull():
            return ic
    return QIcon()


def app_icon() -> QIcon:
    themed = QIcon.fromTheme("lumina")
    if not themed.isNull():
        return themed
    pm = QPixmap(256, 256)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(ORANGE))
    p.drawRoundedRect(16, 16, 224, 224, 48, 48)
    p.setBrush(QColor("white"))
    p.drawEllipse(150, 60, 36, 36)
    p.drawPolygon(QPolygonF([QPointF(40, 200), QPointF(105, 110), QPointF(150, 170),
                             QPointF(180, 135), QPointF(216, 200)]))
    p.end()
    return QIcon(pm)
