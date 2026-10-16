from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image
from PySide6.QtCore import (QFile, QRectF, QSettings, QSize, Qt, QThreadPool,
                            QTimer, QUrl)
from PySide6.QtGui import (QAction, QActionGroup, QColor, QDesktopServices,
                           QGuiApplication, QIcon, QImage, QKeySequence,
                           QPainter, QPalette, QPixmap)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox,
                               QDialog, QDialogButtonBox, QDockWidget,
                               QFileDialog, QFrame, QGraphicsView, QGridLayout,
                               QGroupBox, QHBoxLayout, QInputDialog, QLabel,
                               QListView, QListWidget, QListWidgetItem,
                               QMainWindow, QMenu, QMessageBox, QPushButton,
                               QScrollArea, QSizePolicy, QStackedWidget, QStyle,
                               QTextBrowser, QToolBar, QToolButton, QVBoxLayout,
                               QWidget)

from core.adjustments import (apply_adjustments, f_autocontrast, f_blur,
                              f_grayscale, f_invert, f_sepia, f_sharpen)
from core.constants import (APP_NAME, EXT_TO_FORMAT, MAX_RESIZE_PIXELS,
                            OPEN_FILTER, RS, SAVE_FILTERS, SUPPORTED_EXTS, TR,
                            VERSION)
from core.document import Document
from core.image_io import load_image, save_image_file
from ui.dialogs import DetailsDialog, ResizeDialog
from ui.image_view import CropOverlay, ImageView
from ui.theme import app_icon, apply_theme, themed_icon
from ui.thumbs import ThumbSignals, ThumbTask
from ui.widgets import AdjustPanel
from utils.details import collect_details
from utils.helpers import describe_error, human_size, list_images
from utils.qt_image import pil_to_pixmap, pil_to_qimage


class MainWindow(QMainWindow):
    THUMB = 88

    def __init__(self):
        super().__init__()
        self.settings = QSettings()
        self.doc = Document()
        self._files: list[str] = []
        self._index = -1
        self._index_map: dict[str, int] = {}
        self._folder: str | None = None
        self._items: dict[str, QListWidgetItem] = {}
        self._thumb_gen = 0
        self._thumb_cache: dict[tuple, QPixmap] = {}
        self._syncing = False
        self._icon_specs: list[tuple] = []
        self._image_actions: list[QAction] = []
        self._overlay: CropOverlay | None = None
        self._fs_state: dict | None = None
        self._pb_src = None
        self._pb = None

        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(max(2, min(4, os.cpu_count() or 2)))
        self.thumb_signals = ThumbSignals()
        self.thumb_signals.loaded.connect(self._on_thumb_loaded)

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(30)
        self._preview_timer.timeout.connect(lambda: self._refresh_display())
        self.slide_timer = QTimer(self)
        self.slide_timer.setInterval(3000)
        self.slide_timer.timeout.connect(self._slide_tick)

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.setAcceptDrops(True)
        self.setMinimumSize(360, 280)
        self.resize(1320, 840)

        self._make_placeholder()
        self._build_actions()
        self._build_central()
        self._build_edit_dock()
        self._build_thumb_dock()
        self._build_menus()
        self._build_toolbar()
        self._build_status()
        self._restore_settings()
        self._refresh_icons()
        self._update_ui()

    # ── construction ──────────────────────────────────────────────────────
    def _act(self, text, slot=None, shortcut=None, icon=None, tip=None,
             checkable=False, needs_image=False) -> QAction:
        a = QAction(text, self)
        if icon:
            self._icon_specs.append((a, icon))
        if shortcut:
            seqs = shortcut if isinstance(shortcut, (list, tuple)) else [shortcut]
            a.setShortcuts([QKeySequence(s) for s in seqs])
        plain = text.replace("&", "").replace("…", "")
        hint = f" ({a.shortcut().toString()})" if shortcut else ""
        a.setToolTip(f"{plain}{hint}")
        a.setStatusTip(tip or plain)
        if checkable:
            a.setCheckable(True)
            if slot:
                a.toggled.connect(slot)
        elif slot:
            a.triggered.connect(lambda _=False, s=slot: s())
        if needs_image:
            self._image_actions.append(a)
        self.addAction(a)  # keeps shortcuts alive even when menus/toolbars are hidden
        return a

    def _build_actions(self):
        A = self._act
        self.act_open = A("&Open Image…", self.choose_file, "Ctrl+O", "document-open")
        self.act_show_folder = A("Show in &Files", self.open_containing_folder, "Ctrl+Shift+O",
                                 "folder-open", needs_image=True)
        self.act_save = A("&Save (overwrite original)…", self.save, "Ctrl+S", "document-save",
                          tip="Save changes over the original file (asks for confirmation)")
        self.act_save_as = A("Save &As…", self.save_as, "Ctrl+Shift+S", "document-save-as",
                             needs_image=True)
        self.act_revert = A("Re&vert to Saved", self.revert, None, "document-revert", needs_image=True)
        self.act_copy = A("&Copy Image", self.copy_image, "Ctrl+C", "edit-copy", needs_image=True)
        self.act_background = A("Set as Desktop &Background", self.set_background, None,
                                "preferences-desktop-wallpaper", needs_image=True)
        self.act_trash = A("Move to &Trash…", self.trash_current, "Delete", "user-trash",
                           needs_image=True)
        self.act_quit = A("&Quit", self.close, "Ctrl+Q", "application-exit")

        self.act_undo = A("&Undo", self.undo, "Ctrl+Z", "edit-undo")
        self.act_redo = A("&Redo", self.redo, ["Ctrl+Shift+Z", "Ctrl+Y"], "edit-redo")
        self.act_rot_l = A("Rotate &Left", lambda: self.rotate(False), "Shift+R",
                           "object-rotate-left", needs_image=True)
        self.act_rot_r = A("Rotate &Right", lambda: self.rotate(True), "R",
                           "object-rotate-right", needs_image=True)
        self.act_flip_h = A("Flip &Horizontal", lambda: self.flip(True), "H",
                            "object-flip-horizontal", needs_image=True)
        self.act_flip_v = A("Flip &Vertical", lambda: self.flip(False), "V",
                            "object-flip-vertical", needs_image=True)
        self.act_crop = A("&Crop", self.toggle_crop, "C", ("transform-crop", "image-crop"),
                          checkable=True, needs_image=True,
                          tip="Draw a crop rectangle; press Enter to apply, Esc to cancel")
        self.act_resize = A("Re&size…", self.resize_image, "Ctrl+R", ("transform-scale", "zoom-fit-best"),
                            needs_image=True)

        self.act_prev = A("&Previous Image", self.go_prev, None, "go-previous")
        self.act_next = A("&Next Image", self.go_next, None, "go-next")
        self.act_prev.setToolTip("Previous image (Left)")
        self.act_next.setToolTip("Next image (Right)")
        self.act_prev.setText("&Previous Image\tLeft")
        self.act_next.setText("&Next Image\tRight")
        self.act_first = A("&First Image\tHome", lambda: self.go_to(0))
        self.act_last = A("&Last Image\tEnd", lambda: self.go_to(len(self._files) - 1))

        self.act_zoom_in = A("Zoom &In", lambda: self.view.zoom_by(1.25),
                             ["Ctrl++", "Ctrl+=", "+", "="], "zoom-in", needs_image=True)
        self.act_zoom_out = A("Zoom &Out", lambda: self.view.zoom_by(1 / 1.25),
                              ["Ctrl+-", "-"], "zoom-out", needs_image=True)
        self.act_fit = A("&Fit to Window", lambda: self.view.fit_to_window(True),
                         ["Ctrl+0", "0"], "zoom-fit-best", needs_image=True)
        self.act_actual = A("&Actual Size (100%)", lambda: self.view.set_zoom(1.0),
                            ["Ctrl+1", "1"], "zoom-original", needs_image=True)
        self.act_fullscreen = A("&Full Screen", self.toggle_fullscreen, ["F11", "F"], "view-fullscreen")
        self.act_slideshow = A("&Slideshow", self.toggle_slideshow, "F5", "media-playback-start",
                               checkable=True)
        self.act_details = A("Image &Details…", self.show_details, ["I", "Ctrl+I"], "dialog-information",
                             needs_image=True)
        self.act_help = A("&Keyboard Shortcuts", self.show_shortcuts, ["F1", "?"], "help-keyboard-shortcuts")
        self.act_about = A("&About Lumina", self.show_about, None, "help-about")

    def _build_central(self):
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(12)
        self.page_icon = QLabel()
        self.page_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_title = QLabel()
        f = self.page_title.font(); f.setPointSize(f.pointSize() + 5); f.setBold(True)
        self.page_title.setFont(f)
        self.page_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_text = QLabel()
        self.page_text.setWordWrap(True)
        self.page_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_text.setMaximumWidth(560)
        self.page_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.page_btn = QPushButton("Open Image…")
        self.page_btn.clicked.connect(self.choose_file)
        lay.addStretch()
        lay.addWidget(self.page_icon)
        lay.addWidget(self.page_title)
        lay.addWidget(self.page_text, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self.page_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch()
        self.stack.addWidget(page)

        self.view = ImageView()
        self.view.zoomChanged.connect(lambda z: self.lbl_zoom.setText(f"{z * 100:.0f}%"))
        self.view.filesDropped.connect(self.handle_dropped)
        self.view.activated.connect(self._toggle_fit_actual)
        self.view.customContextMenuRequested.connect(self._context_menu)
        self.stack.addWidget(self.view)
        self._show_welcome()

    def _show_welcome(self):
        self.page_icon.setPixmap(app_icon().pixmap(96, 96))
        self.page_title.setText("Open an image to get started")
        self.page_text.setText("Drag and drop a picture or folder here, or press Ctrl+O.\n"
                               "Supports JPEG, PNG, WebP, GIF, BMP and TIFF.")
        self.page_btn.setText("Open Image…")

    def _show_error_page(self, title: str, text: str):
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)
        self.page_icon.setPixmap(icon.pixmap(64, 64))
        self.page_title.setText(title)
        self.page_text.setText(text + ("\n\nUse the arrow keys to move to another image."
                                       if len(self._files) > 1 else ""))
        self.page_btn.setText("Open Another Image…")

    def _build_edit_dock(self):
        self.edit_dock = QDockWidget("Edit", self)
        self.edit_dock.setObjectName("editDock")
        self.edit_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget()
        self.edit_host = host
        lay = QVBoxLayout(host)
        lay.setSpacing(10)

        def tool_button(action):
            b = QToolButton()
            b.setDefaultAction(action)
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            b.setMinimumHeight(32)
            return b

        g = QGroupBox("Transform")
        grid = QGridLayout(g)
        for i, act in enumerate((self.act_rot_l, self.act_rot_r, self.act_flip_h, self.act_flip_v,
                                 self.act_crop, self.act_resize)):
            grid.addWidget(tool_button(act), i // 2, i % 2)
        lay.addWidget(g)

        # crop options (visible only while cropping)
        self.crop_group = QGroupBox("Crop")
        cl = QVBoxLayout(self.crop_group)
        self.crop_ratio = QComboBox()
        self.crop_ratio.setAccessibleName("Crop aspect ratio")
        for label, val in (("Free", None), ("Original", "orig"), ("Square (1:1)", 1.0),
                           ("4:3", 4 / 3), ("3:2", 3 / 2), ("16:9", 16 / 9),
                           ("3:4 (portrait)", 3 / 4), ("2:3 (portrait)", 2 / 3), ("9:16 (portrait)", 9 / 16)):
            self.crop_ratio.addItem(label, val)
        self.crop_ratio.currentIndexChanged.connect(self._crop_ratio_changed)
        self.crop_size_lbl = QLabel("")
        row = QHBoxLayout()
        ok = QPushButton("Apply Crop")
        cancel = QPushButton("Cancel")
        ok.clicked.connect(self.apply_crop)
        cancel.clicked.connect(self._exit_crop)
        row.addWidget(ok); row.addWidget(cancel)
        cl.addWidget(QLabel("Aspect ratio:"))
        cl.addWidget(self.crop_ratio)
        cl.addWidget(self.crop_size_lbl)
        cl.addLayout(row)
        cl.addWidget(QLabel("<small>Drag the handles or edges. Enter applies, Esc cancels.</small>"))
        self.crop_group.setVisible(False)
        lay.addWidget(self.crop_group)

        self.adjust_panel = AdjustPanel()
        self.adjust_panel.changed.connect(self._preview_timer.start)
        self.adjust_panel.applyClicked.connect(self.apply_adjustments_clicked)
        lay.addWidget(self.adjust_panel)

        fg = QGroupBox("Quick filters")
        fgrid = QGridLayout(fg)
        filters = [("Grayscale", f_grayscale), ("Sepia", f_sepia), ("Invert", f_invert),
                   ("Auto contrast", f_autocontrast), ("Blur", f_blur), ("Sharpen", f_sharpen)]
        for i, (label, fn) in enumerate(filters):
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, l=label, f=fn: self._do_edit(l, f))
            fgrid.addWidget(b, i // 2, i % 2)
        lay.addWidget(fg)
        lay.addStretch()

        scroll.setWidget(host)
        self.edit_dock.setWidget(scroll)
        self.edit_dock.setMinimumWidth(270)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.edit_dock)

    def _make_placeholder(self):
        pm = QPixmap(self.THUMB, self.THUMB)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        col = QApplication.palette().color(QPalette.ColorRole.Mid)
        col.setAlpha(120)
        p.setBrush(col)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(4, 4, self.THUMB - 8, self.THUMB - 8, 8, 8)
        p.end()
        self._placeholder = QIcon(pm)

    def _build_thumb_dock(self):
        self.thumb_dock = QDockWidget("Folder", self)
        self.thumb_dock.setObjectName("thumbDock")
        self.thumb_dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.TopDockWidgetArea)
        lw = QListWidget()
        lw.setViewMode(QListView.ViewMode.IconMode)
        lw.setFlow(QListView.Flow.LeftToRight)
        lw.setWrapping(False)
        lw.setMovement(QListView.Movement.Static)
        lw.setResizeMode(QListView.ResizeMode.Adjust)
        lw.setUniformItemSizes(True)
        lw.setIconSize(QSize(self.THUMB, self.THUMB))
        lw.setSpacing(2)
        lw.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        lw.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        lw.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        lw.setFixedHeight(self.THUMB + 52)
        lw.setFrameShape(QFrame.Shape.NoFrame)
        lw.setAccessibleName("Thumbnails of images in this folder")
        lw.setStyleSheet("QListWidget::item { border-radius: 6px; padding: 3px; }"
                         "QListWidget::item:selected { background: palette(highlight); color: palette(highlighted-text); }")
        lw.currentRowChanged.connect(self._on_thumb_row)
        self.thumbs = lw
        self.thumb_dock.setWidget(lw)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.thumb_dock)

    def _build_menus(self):
        mb = self.menuBar()
        m = mb.addMenu("&File")
        for a in (self.act_open, self.act_show_folder, None, self.act_save, self.act_save_as,
                  self.act_revert, None, self.act_copy, self.act_background, self.act_trash,
                  None, self.act_quit):
            m.addSeparator() if a is None else m.addAction(a)

        m = mb.addMenu("&Edit")
        for a in (self.act_undo, self.act_redo, None, self.act_rot_l, self.act_rot_r, self.act_flip_h,
                  self.act_flip_v, None, self.act_crop, self.act_resize):
            m.addSeparator() if a is None else m.addAction(a)

        m = mb.addMenu("&View")
        for a in (self.act_prev, self.act_next, self.act_first, self.act_last, None,
                  self.act_zoom_in, self.act_zoom_out, self.act_fit, self.act_actual, None,
                  self.act_fullscreen, self.act_slideshow, None):
            m.addSeparator() if a is None else m.addAction(a)
        tv = self.thumb_dock.toggleViewAction(); tv.setText("&Thumbnail Strip"); tv.setShortcut("F9")
        ev = self.edit_dock.toggleViewAction(); ev.setText("&Edit Panel"); ev.setShortcut("F8")
        self.addAction(tv); self.addAction(ev)
        m.addAction(tv); m.addAction(ev)
        theme = m.addMenu("T&heme")
        grp = QActionGroup(self)
        current = str(self.settings.value("theme", "system"))
        for label, key in (("Follow system", "system"), ("Light", "light"), ("Dark", "dark")):
            a = theme.addAction(label)
            a.setCheckable(True)
            a.setChecked(key == current)
            grp.addAction(a)
            a.triggered.connect(lambda _=False, k=key: self.set_theme(k))

        m = mb.addMenu("&Image")
        m.addAction(self.act_background)
        m.addAction(self.act_details)
        m = mb.addMenu("&Help")
        m.addAction(self.act_help)
        m.addAction(self.act_about)

    def _build_toolbar(self):
        tb = QToolBar("Main toolbar", self)
        tb.setObjectName("mainToolbar")
        tb.setMovable(False)
        tb.setIconSize(QSize(22, 22))
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.toolbar = tb
        for a in (self.act_open, self.act_save, None, self.act_prev, self.act_next, None,
                  self.act_zoom_out, self.act_zoom_in, self.act_fit, self.act_actual, None,
                  self.act_rot_l, self.act_rot_r, self.act_flip_h, self.act_flip_v, self.act_crop,
                  self.act_resize, None, self.act_undo, self.act_redo, None,
                  self.act_details, self.act_slideshow, self.act_fullscreen):
            tb.addSeparator() if a is None else tb.addAction(a)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)

    def _build_status(self):
        sb = self.statusBar()
        self.lbl_index, self.lbl_dims, self.lbl_size, self.lbl_zoom = (QLabel() for _ in range(4))
        self.lbl_zoom.setText("100%")
        for lbl in (self.lbl_index, self.lbl_dims, self.lbl_size, self.lbl_zoom):
            lbl.setContentsMargins(8, 0, 8, 0)
            sb.addPermanentWidget(lbl)
        self.lbl_zoom.setAccessibleName("Zoom level")
        self.lbl_index.setAccessibleName("Position in folder")
        self.lbl_dims.setAccessibleName("Image dimensions")
        sb.showMessage("Ready — drop an image anywhere, or press Ctrl+O", 6000)

    def _refresh_icons(self):
        color = QApplication.palette().color(QPalette.ColorRole.WindowText)
        for action, names in self._icon_specs:
            action.setIcon(themed_icon(names, color))

    # ── settings / theme ─────────────────────────────────────────────────
    def _restore_settings(self):
        geo = self.settings.value("geometry")
        if geo:
            self.restoreGeometry(geo)
        state = self.settings.value("windowState")
        if state:
            self.restoreState(state)

    def set_theme(self, mode: str):
        self.settings.setValue("theme", mode)
        apply_theme(QApplication.instance(), mode)
        self._make_placeholder()
        self._refresh_icons()

    # ── drag and drop (anywhere on the window) ───────────────────────────
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        e.acceptProposedAction()
        self.handle_dropped(paths)

    def handle_dropped(self, paths: list):
        if not paths:
            self.show_error("Can't open that item",
                            "Only files and folders stored on this computer can be opened.")
            return
        p = paths[0]
        if os.path.isdir(p):
            files = list_images(p)
            if not files:
                self.show_error("No images found",
                                f"The folder “{os.path.basename(p.rstrip('/'))}” doesn't contain any "
                                "JPEG, PNG, WebP, GIF, BMP or TIFF images.")
                return
            p = files[0]
        if len(paths) > 1:
            self.statusBar().showMessage(f"Opened the first of {len(paths)} dropped items", 4000)
        self.open_path(p, explicit=True)

    # ── keyboard ─────────────────────────────────────────────────────────
    def keyPressEvent(self, e):
        k, mods = e.key(), e.modifiers()
        K = Qt.Key
        if k == K.Key_Escape:
            if self._overlay:
                self._exit_crop(); return
            if self.isFullScreen():
                self._leave_fullscreen(); return
            if self.slide_timer.isActive():
                self.act_slideshow.setChecked(False); return
        elif k in (K.Key_Return, K.Key_Enter) and self._overlay:
            self.apply_crop(); return
        elif not (mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
                          | Qt.KeyboardModifier.MetaModifier)):
            if k in (K.Key_Right, K.Key_PageDown, K.Key_Space): self.go_next(); return
            if k in (K.Key_Left, K.Key_PageUp, K.Key_Backspace): self.go_prev(); return
            if k == K.Key_Home: self.go_to(0); return
            if k == K.Key_End: self.go_to(len(self._files) - 1); return
        super().keyPressEvent(e)

    # ── dialogs ──────────────────────────────────────────────────────────
    def show_error(self, title: str, text: str, details: str | None = None):
        box = QMessageBox(QMessageBox.Icon.Warning, title, text, QMessageBox.StandardButton.Ok, self)
        if details:
            box.setDetailedText(details)
        box.exec()

    def maybe_discard(self) -> bool:
        """Ask what to do with unsaved edits. Returns True if it's safe to continue."""
        if not self.doc.dirty:
            return True
        name = os.path.basename(self.doc.path or "this image")
        box = QMessageBox(QMessageBox.Icon.Question, "Unsaved changes",
                          f"Save your changes to “{name}”?", parent=self)
        box.setInformativeText("If you don't save, your edits will be lost.")
        b_save = box.addButton("Save As…", QMessageBox.ButtonRole.AcceptRole)
        b_discard = box.addButton("Discard Changes", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(b_save)
        box.exec()
        clicked = box.clickedButton()
        if clicked is b_save:
            return self.save_as()
        return clicked is b_discard

    # ── opening / navigation ─────────────────────────────────────────────
    def choose_file(self):
        start = self._folder or str(self.settings.value("last_dir", str(Path.home())))
        path, _ = QFileDialog.getOpenFileName(self, "Open Image", start, OPEN_FILTER)
        if path:
            self.open_path(path, explicit=True)

    def open_path(self, path: str, explicit=False, force=False) -> bool:
        path = os.path.abspath(path)
        if not force and not self.maybe_discard():
            self._sync_thumb_selection()
            return False
        self._exit_crop()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        err, loaded = None, None
        try:
            loaded = load_image(path)
        except Exception as exc:
            err = exc
        finally:
            QApplication.restoreOverrideCursor()

        folder = os.path.dirname(path)
        if folder != self._folder or (path not in self._index_map and
                                      path.lower().endswith(SUPPORTED_EXTS)):
            self._set_folder(folder, path)

        if err is not None or loaded is None:
            title, text = describe_error(path, err or RuntimeError("unknown error"))
            self.doc.clear()
            self._index = self._index_map.get(path, -1)
            self._sync_thumb_selection()
            self.adjust_panel.reset(silent=True)
            self.view.clear_image()
            self._show_error_page(title, text)
            self._update_ui()
            self.statusBar().showMessage(f"Couldn't open “{os.path.basename(path)}”", 6000)
            if explicit:
                self.show_error(title, text)
            return False

        self.doc.load(path, loaded)
        self._index = self._index_map.get(path, -1)
        self.adjust_panel.reset(silent=True)
        self._sync_thumb_selection()
        self._update_ui()
        QApplication.processEvents()
        self._resize_window_to_image()
        self._refresh_display(new_image=True)
        self.settings.setValue("last_dir", folder)
        self.view.setFocus()
        return True

    def _resize_window_to_image(self):
        """Size the window so the canvas matches the image (capped to the screen)."""
        img = self.doc.image
        if img is None or self.isFullScreen():
            return
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        if self.isMaximized():
            self.showNormal()

        iw, ih = img.size
        vp = self.view.viewport().size()
        extra_w = max(0, self.width() - max(1, vp.width()))
        extra_h = max(0, self.height() - max(1, vp.height()))
        max_vw = max(1, avail.width() - extra_w)
        max_vh = max(1, avail.height() - extra_h)
        scale = min(1.0, max_vw / max(1, iw), max_vh / max(1, ih))
        vw = max(1, round(iw * scale))
        vh = max(1, round(ih * scale))
        new_w = min(vw + extra_w, avail.width())
        new_h = min(vh + extra_h, avail.height())
        self.resize(new_w, new_h)

        frame = self.frameGeometry()
        x = avail.x() + max(0, (avail.width() - frame.width()) // 2)
        y = avail.y() + max(0, (avail.height() - frame.height()) // 2)
        self.move(x, y)

    def _set_folder(self, folder: str, current: str | None):
        self._folder = folder
        self._files = list_images(folder)
        self._index_map = {p: i for i, p in enumerate(self._files)}
        self._index = self._index_map.get(current or "", -1)
        self._populate_thumbs()

    def go(self, delta: int):
        n = len(self._files)
        if n == 0:
            return
        if self._index < 0:
            idx = 0 if delta > 0 else n - 1
        else:
            idx = (self._index + delta) % n
            if n == 1:
                return
        self.open_path(self._files[idx])

    def go_next(self): self.go(1)
    def go_prev(self): self.go(-1)

    def go_to(self, idx: int):
        if 0 <= idx < len(self._files) and idx != self._index:
            self.open_path(self._files[idx])

    def _toggle_fit_actual(self):
        if abs(self.view.zoom - 1.0) < 0.01:
            self.view.fit_to_window(True)
        else:
            self.view.set_zoom(1.0, mouse=True)

    def _slide_tick(self):
        if self.doc.dirty or self._overlay:
            return
        self.go_next()

    def toggle_slideshow(self, on: bool):
        if on and len(self._files) < 2:
            self.statusBar().showMessage("Open a folder with at least two images to start a slideshow", 4000)
            self.act_slideshow.blockSignals(True)
            self.act_slideshow.setChecked(False)
            self.act_slideshow.blockSignals(False)
            return
        if on:
            self.slide_timer.start()
            self.statusBar().showMessage("Slideshow running — press Esc or F5 to stop", 4000)
        else:
            self.slide_timer.stop()

    # ── thumbnails ───────────────────────────────────────────────────────
    def _thumb_key(self, path: str):
        try:
            st = os.stat(path)
            return (path, st.st_mtime_ns, st.st_size)
        except OSError:
            return (path, 0, 0)

    def _populate_thumbs(self):
        self._thumb_gen += 1
        gen = self._thumb_gen
        self.pool.clear()
        self._syncing = True
        self.thumbs.clear()
        self._items.clear()
        pending = []
        for i, p in enumerate(self._files):
            it = QListWidgetItem(self._placeholder, os.path.basename(p))
            it.setToolTip(p)
            it.setData(Qt.ItemDataRole.UserRole, p)
            it.setSizeHint(QSize(self.THUMB + 24, self.THUMB + 36))
            self.thumbs.addItem(it)
            self._items[p] = it
            pm = self._thumb_cache.get(self._thumb_key(p))
            if pm is not None:
                it.setIcon(QIcon(pm))
            else:
                pending.append(i)
        self._syncing = False
        centre = max(self._index, 0)
        pending.sort(key=lambda i: abs(i - centre))
        for rank, i in enumerate(pending):
            self.pool.start(ThumbTask(gen, self._files[i], int(self.THUMB * 1.5), self.thumb_signals), -rank)
        self._sync_thumb_selection()

    def _refresh_thumb(self, path: str):
        if path in self._items:
            self.pool.start(ThumbTask(self._thumb_gen, path, int(self.THUMB * 1.5), self.thumb_signals), 1)

    def _on_thumb_loaded(self, gen: int, path: str, qimg: QImage):
        if gen != self._thumb_gen or qimg.isNull():
            return
        item = self._items.get(path)
        if item is None:
            return
        pm = QPixmap.fromImage(qimg)
        self._thumb_cache[self._thumb_key(path)] = pm
        item.setIcon(QIcon(pm))

    def _sync_thumb_selection(self):
        self._syncing = True
        try:
            if 0 <= self._index < self.thumbs.count():
                self.thumbs.setCurrentRow(self._index)
                self.thumbs.scrollToItem(self.thumbs.item(self._index),
                                         QAbstractItemView.ScrollHint.PositionAtCenter)
            else:
                self.thumbs.setCurrentRow(-1)
        finally:
            self._syncing = False

    def _on_thumb_row(self, row: int):
        if self._syncing or row < 0 or row >= len(self._files):
            return
        if self._files[row] != self.doc.path:
            self.open_path(self._files[row])

    # ── display ──────────────────────────────────────────────────────────
    def _preview_base(self) -> Image.Image:
        img = self.doc.image
        if self._pb_src is not img:
            w, h = img.size
            s = min(1.0, 1400 / max(w, h))
            self._pb = img if s >= 1 else img.resize(
                (max(1, round(w * s)), max(1, round(h * s))), RS.BILINEAR, reducing_gap=2.0)
            self._pb_src = img
        return self._pb

    def _refresh_display(self, new_image=False):
        img = self.doc.image
        if img is None:
            self.view.clear_image()
            return
        try:
            params = self.adjust_panel.params()
            if params.is_identity():
                pm = pil_to_pixmap(img)
            else:
                pm = pil_to_pixmap(apply_adjustments(self._preview_base(), params))
        except Exception as exc:
            self.show_error("Couldn't display the image", f"{type(exc).__name__}: {exc}")
            return
        self.view.set_image(pm, QSize(*img.size), fit_new=new_image, has_alpha=img.mode == "RGBA")
        self._update_status()

    def _update_status(self):
        img = self.doc.image
        if img is None:
            self.lbl_index.setText(f"{len(self._files)} images" if self._files else "")
            self.lbl_dims.setText("")
            self.lbl_size.setText("")
            return
        self.lbl_index.setText(f"{self._index + 1} / {len(self._files)}" if self._index >= 0 else "")
        self.lbl_dims.setText(f"{img.width} × {img.height} px")
        if self.doc.dirty:
            self.lbl_size.setText("edited")
        else:
            try:
                self.lbl_size.setText(human_size(os.path.getsize(self.doc.path)))
            except (OSError, TypeError):
                self.lbl_size.setText("")

    def _update_ui(self):
        has = self.doc.image is not None
        for a in self._image_actions:
            a.setEnabled(has)
        self.act_show_folder.setEnabled(has and bool(self.doc.path))
        self.act_save.setEnabled(has and self.doc.dirty)
        self.act_revert.setEnabled(has and self.doc.dirty and bool(self.doc.path))
        nav = len(self._files) > 1
        for a in (self.act_prev, self.act_next, self.act_first, self.act_last, self.act_slideshow):
            a.setEnabled(nav)
        self.act_undo.setEnabled(self.doc.can_undo)
        self.act_redo.setEnabled(self.doc.can_redo)
        self.act_undo.setText(f"&Undo {self.doc.undo_label}" if self.doc.can_undo else "&Undo")
        self.act_redo.setText(f"&Redo {self.doc.redo_label}" if self.doc.can_redo else "&Redo")
        self.edit_host.setEnabled(has)
        self.stack.setCurrentIndex(1 if has else 0)
        name = os.path.basename(self.doc.path) if self.doc.path else ""
        self.setWindowTitle(f"{'● ' if self.doc.dirty else ''}{name} — {APP_NAME}" if name else APP_NAME)
        self._update_status()

    def _context_menu(self, pos):
        if self.doc.image is None:
            return
        m = QMenu(self)
        for a in (self.act_fit, self.act_actual, None, self.act_rot_l, self.act_rot_r, None,
                  self.act_copy, self.act_background, self.act_details, self.act_fullscreen):
            m.addSeparator() if a is None else m.addAction(a)
        m.exec(self.view.mapToGlobal(pos))

    # ── editing ──────────────────────────────────────────────────────────
    def _do_edit(self, label: str, func, clear_adjust=False) -> bool:
        if self.doc.image is None:
            return False
        self._exit_crop()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        err, new = None, None
        try:
            new = func(self.doc.image)
        except Exception as exc:
            err = exc
        finally:
            QApplication.restoreOverrideCursor()
        if err is not None or new is None:
            if isinstance(err, MemoryError):
                self.show_error(f"{label} failed", "There isn't enough memory to do that to this image.")
            else:
                self.show_error(f"{label} failed", f"{type(err).__name__}: {err}")
            return False
        self.doc.commit(label, new)
        if clear_adjust:
            self.adjust_panel.reset(silent=True)
        self._refresh_display()
        self._update_ui()
        self.statusBar().showMessage(label, 2500)
        return True

    def rotate(self, clockwise: bool):
        self._do_edit("Rotate Right" if clockwise else "Rotate Left",
                      lambda im: im.transpose(TR.ROTATE_270 if clockwise else TR.ROTATE_90))

    def flip(self, horizontal: bool):
        self._do_edit("Flip Horizontal" if horizontal else "Flip Vertical",
                      lambda im: im.transpose(TR.FLIP_LEFT_RIGHT if horizontal else TR.FLIP_TOP_BOTTOM))

    def resize_image(self):
        if self.doc.image is None:
            return
        w, h = self.doc.image.size
        dlg = ResizeDialog(w, h, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        nw, nh, method = dlg.values()
        if (nw, nh) == (w, h):
            return
        if nw * nh > MAX_RESIZE_PIXELS:
            self.show_error("Image would be too large",
                            f"{nw} × {nh} pixels is more than Lumina can safely handle "
                            f"(limit ≈ {MAX_RESIZE_PIXELS // 1_000_000} megapixels). Choose a smaller size.")
            return
        self._do_edit(f"Resize to {nw}×{nh}", lambda im: im.resize((nw, nh), method))

    def apply_adjustments_clicked(self):
        p = self.adjust_panel.params()
        if p.is_identity():
            return
        self._do_edit("Adjust Colors", lambda im: apply_adjustments(im, p), clear_adjust=True)

    def undo(self):
        label = self.doc.undo()
        if label:
            self._after_history(f"Undid {label}")

    def redo(self):
        label = self.doc.redo()
        if label:
            self._after_history(f"Redid {label}")

    def _after_history(self, msg: str):
        self._exit_crop()
        self._refresh_display()
        self._update_ui()
        self.statusBar().showMessage(msg, 2500)

    # ── cropping ─────────────────────────────────────────────────────────
    def toggle_crop(self, on: bool):
        if on:
            self._enter_crop()
        else:
            self._exit_crop()

    def _enter_crop(self):
        if self.doc.image is None or self._overlay is not None:
            return
        self.adjust_panel.reset(silent=True)
        self._refresh_display()
        w, h = self.doc.image.size
        self._overlay = CropOverlay(QRectF(0, 0, w, h), self._crop_changed)
        self.view.scene().addItem(self._overlay)
        self.view.crop_active = True
        self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.crop_ratio.blockSignals(True)
        self.crop_ratio.setCurrentIndex(0)
        self.crop_ratio.blockSignals(False)
        self.crop_group.setVisible(True)
        self.edit_dock.show()
        self._crop_changed()
        self.statusBar().showMessage("Crop: drag the handles, press Enter to apply or Esc to cancel", 6000)

    def _exit_crop(self):
        if self._overlay is not None:
            self.view.scene().removeItem(self._overlay)
            self._overlay = None
        self.view.crop_active = False
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.crop_group.setVisible(False)
        if self.act_crop.isChecked():
            self.act_crop.blockSignals(True)
            self.act_crop.setChecked(False)
            self.act_crop.blockSignals(False)

    def _crop_changed(self):
        if self._overlay:
            r = self._overlay.rect
            self.crop_size_lbl.setText(f"Selection: {round(r.width())} × {round(r.height())} px")

    def _crop_ratio_changed(self):
        if not self._overlay:
            return
        val = self.crop_ratio.currentData()
        if val == "orig" and self.doc.image:
            val = self.doc.image.width / self.doc.image.height
        self._overlay.set_ratio(val)

    def apply_crop(self):
        if not self._overlay or self.doc.image is None:
            return
        r = self._overlay.rect
        iw, ih = self.doc.image.size
        l, t = max(0, round(r.left())), max(0, round(r.top()))
        rr, b = min(iw, round(r.right())), min(ih, round(r.bottom()))
        if rr - l < 1 or b - t < 1:
            return
        if (l, t, rr, b) == (0, 0, iw, ih):
            self._exit_crop()
            self.statusBar().showMessage("Nothing to crop — the selection covers the whole image", 4000)
            return
        box = (l, t, rr, b)
        self._do_edit(f"Crop to {rr - l}×{b - t}", lambda im: im.crop(box).copy())

    # ── saving ───────────────────────────────────────────────────────────
    def save(self) -> bool:
        """Overwrite the original file — always after an explicit confirmation."""
        doc = self.doc
        if doc.image is None:
            return False
        if not doc.dirty:
            self.statusBar().showMessage("No changes to save", 3000)
            return True
        ext = os.path.splitext(doc.path or "")[1].lower()
        if not doc.path or ext not in EXT_TO_FORMAT:
            return self.save_as()
        name = os.path.basename(doc.path)
        notes = []
        if EXT_TO_FORMAT[ext] == "JPEG":
            notes.append("JPEG is a lossy format, so saving re-compresses the picture.")
        if doc.meta and doc.meta.animated:
            notes.append("This file is animated; only the current frame will be saved.")
        box = QMessageBox(QMessageBox.Icon.Warning, "Overwrite original?",
                          f"Replace “{name}” with your edited version?", parent=self)
        box.setInformativeText("The original file will be permanently replaced. This can't be undone."
                               + ("\n\n" + "\n".join(notes) if notes else ""))
        b_over = box.addButton("Overwrite", QMessageBox.ButtonRole.DestructiveRole)
        b_as = box.addButton("Save As…", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(b_as)
        box.exec()
        clicked = box.clickedButton()
        if clicked is b_over:
            return self._write(doc.path)
        if clicked is b_as:
            return self.save_as()
        return False

    def save_as(self) -> bool:
        doc = self.doc
        if doc.image is None:
            return False
        src = doc.path or os.path.join(str(self.settings.value("last_dir", str(Path.home()))), "image.png")
        stem, ext = os.path.splitext(os.path.basename(src))
        if ext.lower() not in EXT_TO_FORMAT:
            ext = ".png"
        suggested = os.path.join(os.path.dirname(src), f"{stem}_edited{ext}")
        default_filter = next((f for f, e in SAVE_FILTERS
                               if ext.lower() in f.replace("*", "").split("(")[1]), SAVE_FILTERS[0][0])
        path, chosen = QFileDialog.getSaveFileName(
            self, "Save Image As", suggested, ";;".join(f for f, _ in SAVE_FILTERS), default_filter)
        if not path:
            return False
        e = os.path.splitext(path)[1].lower()
        if e not in EXT_TO_FORMAT:
            e = dict(SAVE_FILTERS).get(chosen, ".png")
            path += e
            if os.path.exists(path):
                ans = QMessageBox.question(self, "Replace file?",
                                           f"“{os.path.basename(path)}” already exists. Replace it?",
                                           QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                           QMessageBox.StandardButton.No)
                if ans != QMessageBox.StandardButton.Yes:
                    return False
        quality = None
        if EXT_TO_FORMAT[e] in ("JPEG", "WEBP"):
            q, ok = QInputDialog.getInt(self, "Image Quality",
                                        "Quality (1 = smallest file, 100 = best quality):",
                                        int(self.settings.value("quality", 92)), 1, 100)
            if not ok:
                return False
            self.settings.setValue("quality", q)
            quality = q
        return self._write(path, quality)

    def _write(self, path: str, quality: int | None = None) -> bool:
        ext = os.path.splitext(path)[1].lower()
        fmt = EXT_TO_FORMAT[ext]
        if quality is None:
            quality = int(self.settings.value("quality", 92))
        directory = os.path.dirname(path) or "."
        tmp, err = None, None
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            fd, tmp = tempfile.mkstemp(prefix=".lumina-", suffix=ext, dir=directory)
            os.close(fd)
            save_image_file(self.doc.image, tmp, fmt, quality, self.doc.meta)
            try:
                shutil.copymode(path, tmp)
            except OSError:
                os.chmod(tmp, 0o644)
            os.replace(tmp, path)
            tmp = None
        except Exception as exc:
            err = exc
        finally:
            if tmp and os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            QApplication.restoreOverrideCursor()
        if err is not None:
            if isinstance(err, PermissionError):
                msg = f"You don't have permission to write to “{directory}”."
            elif isinstance(err, OSError) and getattr(err, "errno", None) == 28:
                msg = "There isn't enough free disk space."
            else:
                msg = f"{type(err).__name__}: {err}"
            self.show_error("Couldn't save the image", msg)
            return False

        self.doc.mark_saved(path, fmt)
        new_folder = os.path.dirname(path)
        if new_folder != self._folder or path not in self._index_map:
            self._set_folder(new_folder, path)
        else:
            self._index = self._index_map[path]
            self._refresh_thumb(path)
        self._sync_thumb_selection()
        self._update_ui()
        try:
            size = human_size(os.path.getsize(path))
        except OSError:
            size = ""
        self.statusBar().showMessage(f"Saved “{os.path.basename(path)}” ({size})", 5000)
        return True

    def revert(self):
        if not (self.doc.path and self.doc.dirty):
            return
        ans = QMessageBox.question(self, "Revert to saved?",
                                   "Discard all unsaved edits and reload the file from disk?",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                   QMessageBox.StandardButton.Cancel)
        if ans == QMessageBox.StandardButton.Yes:
            self.open_path(self.doc.path, force=True)

    # ── file operations ──────────────────────────────────────────────────
    def copy_image(self):
        if self.doc.image is not None:
            QGuiApplication.clipboard().setImage(pil_to_qimage(self.doc.image))
            self.statusBar().showMessage("Image copied to the clipboard", 3000)

    def set_background(self):
        if self.doc.image is None:
            return
        path = self.doc.path
        if self.doc.dirty or not path:
            cache_dir = Path(
                self.settings.value("wallpaper_cache", str(Path.home() / ".cache" / "lumina"))
            )
            try:
                cache_dir.mkdir(parents=True, exist_ok=True)
                path = str(cache_dir / "wallpaper.png")
                self.doc.image.save(path, format="PNG")
            except (OSError, ValueError) as exc:
                self.show_error("Couldn't set desktop background",
                                f"Lumina could not prepare the image:\n{exc}")
                return

        uri = QUrl.fromLocalFile(path).toString()
        if shutil.which("gsettings"):
            result = subprocess.run(
                ["gsettings", "set", "org.gnome.desktop.background", "picture-uri", uri],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                subprocess.run(
                    ["gsettings", "set", "org.gnome.desktop.background", "picture-uri-dark", uri],
                    capture_output=True, text=True,
                )
                self.statusBar().showMessage("Desktop background updated", 4000)
                return
        if shutil.which("plasma-apply-wallpaperimage"):
            result = subprocess.run(["plasma-apply-wallpaperimage", path],
                                    capture_output=True, text=True)
            if result.returncode == 0:
                self.statusBar().showMessage("Desktop background updated", 4000)
                return
        self.show_error(
            "Couldn't set desktop background",
            "Lumina could not find a supported desktop wallpaper service. "
            "GNOME/Ubuntu requires gsettings; KDE Plasma requires "
            "plasma-apply-wallpaperimage.",
        )

    def open_containing_folder(self):
        if self.doc.path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self.doc.path)))

    def trash_current(self):
        path = self.doc.path
        if not path:
            return
        name = os.path.basename(path)
        box = QMessageBox(QMessageBox.Icon.Question, "Move to Trash?",
                          f"Move “{name}” to the Trash?", parent=self)
        box.setInformativeText("You can restore it from the Trash later.")
        b_yes = box.addButton("Move to Trash", QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(cancel)
        box.exec()
        if box.clickedButton() is not b_yes:
            return
        res = QFile.moveToTrash(path)
        ok = res[0] if isinstance(res, tuple) else bool(res)
        if not ok:
            try:
                ok = subprocess.run(["gio", "trash", path], capture_output=True).returncode == 0
            except Exception:
                ok = False
        if not ok:
            self.show_error("Couldn't move to Trash", f"“{name}” could not be moved to the Trash. "
                            "Check that you have permission to modify this folder.")
            return
        old = self._index
        self._set_folder(self._folder, None)
        self.doc.clear()
        if self._files:
            self.open_path(self._files[min(max(old, 0), len(self._files) - 1)], force=True)
        else:
            self.view.clear_image()
            self._show_welcome()
            self._update_ui()
        self.statusBar().showMessage(f"Moved “{name}” to the Trash", 4000)

    # ── info dialogs ─────────────────────────────────────────────────────
    def show_details(self):
        if self.doc.image is None:
            return
        pos = f"{self._index + 1} of {len(self._files)}" if self._index >= 0 else ""
        DetailsDialog(collect_details(self.doc, pos), self).exec()

    def show_shortcuts(self):
        rows = [
            ("Open image", "Ctrl+O"), ("Next / previous image", "→ ← , Page Down / Up, Space / Backspace"),
            ("First / last image", "Home / End"), ("Zoom in / out", "+ / − , or mouse wheel"),
            ("Fit to window", "0"), ("Actual size (100%)", "1"), ("Toggle fit ↔ 100%", "Double-click"),
            ("Full screen", "F or F11   (Esc to leave)"), ("Slideshow", "F5"),
            ("Rotate right / left", "R / Shift+R"), ("Flip horizontal / vertical", "H / V"),
            ("Crop", "C   (Enter = apply, Esc = cancel)"), ("Resize", "Ctrl+R"),
            ("Undo / redo", "Ctrl+Z / Ctrl+Shift+Z (or Ctrl+Y)"), ("Save (overwrite)", "Ctrl+S"),
            ("Save as", "Ctrl+Shift+S"), ("Copy image", "Ctrl+C"), ("Image details", "I"),
            ("Move to Trash", "Delete"), ("Show in Files", "Ctrl+Shift+O"),
            ("Toggle thumbnails / edit panel", "F9 / F8"), ("This help", "F1"), ("Quit", "Ctrl+Q"),
        ]
        html = "<table cellpadding='4'>" + "".join(
            f"<tr><td><b>{a}</b></td><td>{b}</td></tr>" for a, b in rows) + "</table>"
        dlg = QDialog(self)
        dlg.setWindowTitle("Keyboard Shortcuts")
        dlg.resize(560, 560)
        lay = QVBoxLayout(dlg)
        tb = QTextBrowser(); tb.setHtml(html); tb.setAccessibleName("Keyboard shortcuts")
        lay.addWidget(tb)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(dlg.accept)
        lay.addWidget(box)
        dlg.exec()

    def show_about(self):
        QMessageBox.about(self, f"About {APP_NAME}",
                          f"<h3>{APP_NAME} {VERSION}</h3>"
                          "<p>A fast, friendly image viewer and editor for Ubuntu.</p>"
                          "<p>Built with Python, Qt (PySide6) and Pillow.</p>")

    # ── full screen ──────────────────────────────────────────────────────
    def toggle_fullscreen(self):
        if self.isFullScreen():
            self._leave_fullscreen()
        else:
            self._fs_state = {
                "max": self.isMaximized(), "thumbs": self.thumb_dock.isVisible(),
                "edit": self.edit_dock.isVisible(), "menu": self.menuBar().isVisible(),
                "tool": self.toolbar.isVisible(), "status": self.statusBar().isVisible(),
            }
            self.menuBar().hide(); self.toolbar.hide(); self.statusBar().hide()
            self.thumb_dock.hide(); self.edit_dock.hide()
            self.showFullScreen()

    def _leave_fullscreen(self):
        s = self._fs_state or {}
        self.menuBar().setVisible(s.get("menu", True))
        self.toolbar.setVisible(s.get("tool", True))
        self.statusBar().setVisible(s.get("status", True))
        self.thumb_dock.setVisible(s.get("thumbs", True))
        self.edit_dock.setVisible(s.get("edit", True))
        self.showMaximized() if s.get("max") else self.showNormal()

    # ── shutdown ─────────────────────────────────────────────────────────
    def closeEvent(self, e):
        if not self.maybe_discard():
            e.ignore()
            return
        if self.isFullScreen():
            self._leave_fullscreen()
        self.slide_timer.stop()
        self.pool.clear()
        self.pool.waitForDone(1500)
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        e.accept()
