from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QPainter, QPainterPath, QPen,
                           QPixmap, QTransform)
from PySide6.QtWidgets import (QFrame, QGraphicsItem, QGraphicsPixmapItem,
                               QGraphicsRectItem, QGraphicsScene, QGraphicsView)


class CropOverlay(QGraphicsItem):
    """Interactive crop rectangle (image coordinates == scene coordinates)."""
    MIN = 8.0

    def __init__(self, bounds: QRectF, on_change=None):
        super().__init__()
        self._bounds = QRectF(bounds)
        mx, my = bounds.width() * 0.08, bounds.height() * 0.08
        self.rect = bounds.adjusted(mx, my, -mx, -my)
        self.ratio: float | None = None
        self._on_change = on_change
        self._mode: str | None = None
        self._press = QPointF()
        self._orig = QRectF()
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setZValue(100)

    # geometry ----------------------------------------------------------
    def boundingRect(self) -> QRectF:
        return self._bounds.adjusted(-600, -600, 600, 600)

    def _view_scale(self) -> float:
        sc = self.scene()
        if sc and sc.views():
            return abs(sc.views()[0].transform().m11()) or 1.0
        return 1.0

    def _hit(self, pos: QPointF):
        s = self._view_scale()
        tol = 10.0 / s
        r = self.rect
        pts = {
            "tl": r.topLeft(), "tr": r.topRight(), "bl": r.bottomLeft(), "br": r.bottomRight(),
            "t": QPointF(r.center().x(), r.top()), "b": QPointF(r.center().x(), r.bottom()),
            "l": QPointF(r.left(), r.center().y()), "r": QPointF(r.right(), r.center().y()),
        }
        best, best_d = None, tol * tol
        for name, pt in pts.items():
            d = (pt.x() - pos.x()) ** 2 + (pt.y() - pos.y()) ** 2
            if d <= best_d:
                best, best_d = name, d
        if best:
            return best
        inside_x = r.left() - tol <= pos.x() <= r.right() + tol
        inside_y = r.top() - tol <= pos.y() <= r.bottom() + tol
        if inside_y and abs(pos.x() - r.left()) <= tol: return "l"
        if inside_y and abs(pos.x() - r.right()) <= tol: return "r"
        if inside_x and abs(pos.y() - r.top()) <= tol: return "t"
        if inside_x and abs(pos.y() - r.bottom()) <= tol: return "b"
        if r.contains(pos):
            return "move"
        return None

    def set_ratio(self, ratio: float | None):
        self.ratio = ratio
        if ratio:
            r = self.rect
            w = min(r.width(), r.height() * ratio)
            h = w / ratio
            c = r.center()
            self.rect = QRectF(c.x() - w / 2, c.y() - h / 2, w, h)
        self.update()
        self._notify()

    def _notify(self):
        if self._on_change:
            self._on_change()

    # painting ----------------------------------------------------------
    def paint(self, p: QPainter, option, widget=None):
        s = p.worldTransform().m11() or 1.0
        shade = QPainterPath()
        shade.addRect(self._bounds)
        shade.addRect(self.rect)
        p.fillPath(shade, QBrush(QColor(0, 0, 0, 150)))

        pen = QPen(QColor("white"), 1.0)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(self.rect)

        grid = QPen(QColor(255, 255, 255, 90), 1.0)
        grid.setCosmetic(True)
        p.setPen(grid)
        r = self.rect
        for i in (1, 2):
            x = r.left() + r.width() * i / 3
            y = r.top() + r.height() * i / 3
            p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))

        hs = 9.0 / s
        edge = QPen(QColor(0, 0, 0, 200), 1.0)
        edge.setCosmetic(True)
        p.setPen(edge)
        p.setBrush(QBrush(QColor("white")))
        for pt in (r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight(),
                   QPointF(r.center().x(), r.top()), QPointF(r.center().x(), r.bottom()),
                   QPointF(r.left(), r.center().y()), QPointF(r.right(), r.center().y())):
            p.drawRect(QRectF(pt.x() - hs / 2, pt.y() - hs / 2, hs, hs))

    # interaction -------------------------------------------------------
    def hoverMoveEvent(self, e):
        m = self._hit(e.pos())
        cursors = {
            "tl": Qt.CursorShape.SizeFDiagCursor, "br": Qt.CursorShape.SizeFDiagCursor,
            "tr": Qt.CursorShape.SizeBDiagCursor, "bl": Qt.CursorShape.SizeBDiagCursor,
            "t": Qt.CursorShape.SizeVerCursor, "b": Qt.CursorShape.SizeVerCursor,
            "l": Qt.CursorShape.SizeHorCursor, "r": Qt.CursorShape.SizeHorCursor,
            "move": Qt.CursorShape.SizeAllCursor,
        }
        if m:
            self.setCursor(cursors[m])
        else:
            self.unsetCursor()

    def mousePressEvent(self, e):
        m = self._hit(e.pos())
        if not m:
            e.ignore()
            return
        self._mode, self._press, self._orig = m, e.pos(), QRectF(self.rect)
        e.accept()

    def mouseMoveEvent(self, e):
        if not self._mode:
            return
        d = e.pos() - self._press
        o, bd, m = self._orig, self._bounds, self._mode
        if m == "move":
            x = min(max(o.x() + d.x(), bd.left()), bd.right() - o.width())
            y = min(max(o.y() + d.y(), bd.top()), bd.bottom() - o.height())
            self.rect = QRectF(x, y, o.width(), o.height())
        else:
            l, t, r, b = o.left(), o.top(), o.right(), o.bottom()
            if "l" in m: l = max(bd.left(), min(o.left() + d.x(), o.right() - self.MIN))
            if "r" in m: r = min(bd.right(), max(o.right() + d.x(), o.left() + self.MIN))
            if "t" in m: t = max(bd.top(), min(o.top() + d.y(), o.bottom() - self.MIN))
            if "b" in m: b = min(bd.bottom(), max(o.bottom() + d.y(), o.top() + self.MIN))
            if self.ratio:
                ra = self.ratio
                if m in ("l", "r"):
                    h = (r - l) / ra
                    cy = o.center().y()
                    t, b = cy - h / 2, cy + h / 2
                elif m in ("t", "b"):
                    w = (b - t) * ra
                    cx = o.center().x()
                    l, r = cx - w / 2, cx + w / 2
                else:
                    h = (r - l) / ra
                    if "t" in m: t = b - h
                    else: b = t + h
            new = QRectF(QPointF(l, t), QPointF(r, b))
            if self.ratio and not bd.adjusted(-0.01, -0.01, 0.01, 0.01).contains(new):
                return
            if new.width() < self.MIN or new.height() < self.MIN:
                return
            self.rect = new
        self.update()
        self._notify()

    def mouseReleaseEvent(self, e):
        self._mode = None


class ImageView(QGraphicsView):
    zoomChanged = Signal(float)
    filesDropped = Signal(list)
    activated = Signal()
    MIN_ZOOM, MAX_ZOOM = 0.02, 64.0
    _PASS_KEYS = (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down,
                  Qt.Key.Key_PageUp, Qt.Key.Key_PageDown, Qt.Key.Key_Home, Qt.Key.Key_End,
                  Qt.Key.Key_Space, Qt.Key.Key_Backspace)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        pm = QPixmap(16, 16)
        pm.fill(QColor("#bdbdbd"))
        p = QPainter(pm)
        p.fillRect(0, 0, 8, 8, QColor("#8f8f8f"))
        p.fillRect(8, 8, 8, 8, QColor("#8f8f8f"))
        p.end()
        self._checker_pm = pm
        self._checker = QGraphicsRectItem()
        self._checker.setPen(QPen(Qt.PenStyle.NoPen))
        self._checker.setZValue(-1)
        self._checker.setVisible(False)
        self._item = QGraphicsPixmapItem()
        self._item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self._scene.addItem(self._checker)
        self._scene.addItem(self._item)

        self.setBackgroundBrush(QBrush(QColor("#202020")))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setAcceptDrops(True)
        self.setAccessibleName("Image canvas")
        self.setAccessibleDescription("Shows the current image. Scroll to zoom, drag to pan.")

        self._zoom = 1.0
        self._fit = True
        self._fit_upscale = True
        self._size = QSize()
        self.crop_active = False

    # content -----------------------------------------------------------
    def clear_image(self):
        self._item.setPixmap(QPixmap())
        self._checker.setVisible(False)
        self._size = QSize()

    def set_image(self, pm: QPixmap, logical: QSize, fit_new=False, has_alpha=False):
        size_changed = logical != self._size
        self._size = QSize(logical)
        self._item.setPixmap(pm)
        self._item.setTransform(QTransform.fromScale(
            logical.width() / max(1, pm.width()), logical.height() / max(1, pm.height())))
        rect = QRectF(0, 0, logical.width(), logical.height())
        self._checker.setRect(rect)
        self._checker.setVisible(has_alpha)
        self._scene.setSceneRect(rect)
        if fit_new:
            self.fit_to_window(allow_upscale=True)
        elif self._fit:
            self._apply_fit()
        else:
            if size_changed:
                self.centerOn(rect.center())
            self._after_zoom()

    # zoom --------------------------------------------------------------
    @property
    def zoom(self) -> float:
        return self._zoom

    def _fit_zoom(self, allow_upscale=None) -> float:
        if self._size.isEmpty():
            return 1.0
        vp = self.viewport().size()
        z = min(max(vp.width() - 2, 1) / self._size.width(),
                max(vp.height() - 2, 1) / self._size.height())
        if allow_upscale is None:
            allow_upscale = self._fit_upscale
        if not allow_upscale:
            z = min(z, 1.0)
        return max(self.MIN_ZOOM, min(self.MAX_ZOOM, z))

    def _min_zoom(self) -> float:
        """Smallest allowed zoom: the image still fills/fits the window."""
        return self._fit_zoom(allow_upscale=True)

    def _apply_fit(self):
        z = self._fit_zoom()
        self.resetTransform()
        self.scale(z, z)
        self._zoom = z
        self.centerOn(self._scene.sceneRect().center())
        self._after_zoom()

    def fit_to_window(self, allow_upscale=True):
        if self._size.isEmpty():
            return
        self._fit, self._fit_upscale = True, allow_upscale
        self._apply_fit()

    def set_zoom(self, z: float, mouse=False):
        if self._size.isEmpty():
            return
        min_z = self._min_zoom()
        z = max(min_z, min(self.MAX_ZOOM, z))
        if z <= min_z + 1e-6:
            self.fit_to_window(allow_upscale=True)
            return
        self._fit = False
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse if mouse
                                     else QGraphicsView.ViewportAnchor.AnchorViewCenter)
        f = z / self._zoom
        self.scale(f, f)
        self._zoom = z
        self._after_zoom()

    def zoom_by(self, factor: float, mouse=False):
        self.set_zoom(self._zoom * factor, mouse)

    def _after_zoom(self):
        mode = (Qt.TransformationMode.SmoothTransformation if self._zoom < 3.0
                else Qt.TransformationMode.FastTransformation)
        self._item.setTransformationMode(mode)
        brush = QBrush(self._checker_pm)
        brush.setTransform(QTransform.fromScale(1 / self._zoom, 1 / self._zoom))
        self._checker.setBrush(brush)
        self.zoomChanged.emit(self._zoom)

    # events ------------------------------------------------------------
    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._size.isEmpty():
            return
        if self._fit or self._zoom < self._min_zoom():
            self._apply_fit()

    def wheelEvent(self, e):
        dy = e.angleDelta().y()
        if dy == 0 or self._size.isEmpty():
            super().wheelEvent(e)
            return
        self.zoom_by(1.2 ** (dy / 120.0), mouse=True)
        e.accept()

    def keyPressEvent(self, e):
        if e.key() in self._PASS_KEYS:
            e.ignore()  # let the main window handle navigation
            return
        super().keyPressEvent(e)

    def mouseDoubleClickEvent(self, e):
        if not self.crop_active:
            self.activated.emit()
        super().mouseDoubleClickEvent(e)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        e.acceptProposedAction()
        self.filesDropped.emit(paths)
