"""Windows 95 look: palette, bevels, caption buttons, a frameless window, a progress bar.

Adapted from Floppy's dialogs (KosmoStars). Widgets inside use Qt's classic "Windows" style with a
Win95 palette, which already draws Win95 buttons, check boxes, sliders and menus.
"""

from PyQt6.QtCore import QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPalette, QPen, QPixmap, QPolygon
from PyQt6.QtWidgets import QAbstractButton, QApplication, QVBoxLayout, QWidget

SILVER = QColor("#C0C0C0")
LIGHT = QColor("#DFDFDF")
WHITE = QColor("#FFFFFF")
GRAY = QColor("#808080")
BLACK = QColor("#000000")
NAVY = QColor("#000080")
INACTIVE = QColor("#808080")

TITLE_H = 18
FRAME = 4

APP_QSS = """
QMenuBar { background: #C0C0C0; }
QMenuBar::item { padding: 2px 7px; background: transparent; color: #000000; }
QMenuBar::item:selected { background: #000080; color: #FFFFFF; }
QMenu { background: #C0C0C0; color: #000000; border-top: 2px solid #FFFFFF; border-left: 2px solid #FFFFFF;
        border-right: 2px solid #404040; border-bottom: 2px solid #404040; padding: 2px; }
QMenu::item { padding: 3px 24px 3px 22px; }
QMenu::item:selected { background: #000080; color: #FFFFFF; }
QMenu::item:disabled { color: #808080; }
QMenu::separator { height: 2px; margin: 3px 2px; border-top: 1px solid #808080; border-bottom: 1px solid #FFFFFF; }
QLabel#error { color: #800000; }
"""


def ui_font(bold: bool = False, size: int = 8) -> QFont:
    font = QFont("MS Sans Serif")
    font.setPointSize(size)
    font.setBold(bold)
    return font


def apply_theme(app: QApplication) -> None:
    app.setStyle("Windows")
    pal = QPalette()
    for role, color in (
        (QPalette.ColorRole.Window, SILVER),
        (QPalette.ColorRole.Button, SILVER),
        (QPalette.ColorRole.Base, WHITE),
        (QPalette.ColorRole.AlternateBase, SILVER),
        (QPalette.ColorRole.Text, BLACK),
        (QPalette.ColorRole.WindowText, BLACK),
        (QPalette.ColorRole.ButtonText, BLACK),
        (QPalette.ColorRole.Highlight, NAVY),
        (QPalette.ColorRole.HighlightedText, WHITE),
        (QPalette.ColorRole.Light, WHITE),
        (QPalette.ColorRole.Midlight, LIGHT),
        (QPalette.ColorRole.Mid, GRAY),
        (QPalette.ColorRole.Dark, GRAY),
        (QPalette.ColorRole.Shadow, BLACK),
        (QPalette.ColorRole.ToolTipBase, QColor("#FFFFE1")),
        (QPalette.ColorRole.ToolTipText, BLACK),
    ):
        pal.setColor(role, color)
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, GRAY)
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, GRAY)
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, GRAY)
    app.setPalette(pal)
    app.setFont(ui_font())
    app.setStyleSheet(APP_QSS)


def bevel(p: QPainter, r: QRect, outer_light: QColor, outer_dark: QColor,
          inner_light: QColor, inner_dark: QColor) -> None:
    """Double Win95 bevel around rect r (inclusive)."""
    for (tl, br), inset in (((outer_light, outer_dark), 0), ((inner_light, inner_dark), 1)):
        x0, y0, x1, y1 = r.left() + inset, r.top() + inset, r.right() - inset, r.bottom() - inset
        p.setPen(tl)
        p.drawLine(x0, y0, x1 - 1, y0)
        p.drawLine(x0, y0, x0, y1 - 1)
        p.setPen(br)
        p.drawLine(x0, y1, x1, y1)
        p.drawLine(x1, y0, x1, y1)


def raised(p: QPainter, r: QRect) -> None:
    bevel(p, r, LIGHT, BLACK, WHITE, GRAY)


def sunken(p: QPainter, r: QRect) -> None:
    bevel(p, r, GRAY, WHITE, BLACK, LIGHT)


def sunken_thin(p: QPainter, r: QRect) -> None:
    """Single-pixel sunken border: status bar panels."""
    p.setPen(GRAY)
    p.drawLine(r.left(), r.top(), r.right() - 1, r.top())
    p.drawLine(r.left(), r.top(), r.left(), r.bottom() - 1)
    p.setPen(WHITE)
    p.drawLine(r.left(), r.bottom(), r.right(), r.bottom())
    p.drawLine(r.right(), r.top(), r.right(), r.bottom())


def icon_pixmap(kind: str) -> QPixmap:
    """Win95 message icons: red cross, blue "i"."""
    pm = QPixmap(32, 32)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setPen(QPen(BLACK, 1))
    if kind == "error":
        p.setBrush(QColor("#FF0000"))
        p.drawEllipse(QRect(2, 2, 27, 27))
        p.setPen(QPen(WHITE, 4))
        p.drawLine(10, 10, 21, 21)
        p.drawLine(21, 10, 10, 21)
    else:
        p.setBrush(WHITE)
        p.drawEllipse(QRect(2, 2, 27, 27))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#0000FF"))
        p.drawRect(14, 7, 4, 4)
        p.drawRect(14, 13, 4, 12)
        p.drawRect(12, 13, 2, 2)
        p.drawRect(12, 23, 8, 2)
    p.end()
    return pm


class CaptionButton(QAbstractButton):
    """Title bar button: close, minimize, maximize or restore, with pixel glyphs."""

    def __init__(self, kind: str, parent: QWidget):
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(16, 14)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def sizeHint(self) -> QSize:
        return QSize(16, 14)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        r = self.rect()
        p.fillRect(r, SILVER)
        down = self.isDown()
        if down:
            bevel(p, r, BLACK, WHITE, GRAY, LIGHT)
        else:
            raised(p, r)
        o = 1 if down else 0
        p.translate(o, o)
        p.setPen(BLACK)
        if self.kind == "close":
            for i in range(6):
                for dx in (0, 1):
                    p.drawPoint(4 + i + dx, 3 + i)
                    p.drawPoint(9 - i + dx, 3 + i)
        elif self.kind == "min":
            p.fillRect(4, 9, 6, 2, BLACK)
        elif self.kind == "max":
            p.drawRect(3, 2, 8, 7)
            p.drawLine(3, 3, 11, 3)
        else:   # restore: two overlapping windows
            p.drawRect(5, 1, 6, 5)
            p.drawLine(5, 2, 11, 2)
            p.fillRect(3, 4, 7, 6, SILVER)
            p.drawRect(3, 4, 6, 5)
            p.drawLine(3, 5, 9, 5)
        p.end()


class Win95Frame(QWidget):
    """A frameless top-level window painted like Windows 95: navy title bar, beveled border.

    Content goes into self.body. A resizable frame can be resized by its edges, maximized with the
    caption button or a title bar double-click, and is dragged by the title bar.
    """

    close_requested = pyqtSignal()

    def __init__(self, title: str, parent: QWidget | None = None, resizable: bool = False,
                 icon: QPixmap | None = None, closable: bool = True):
        flags = Qt.WindowType.FramelessWindowHint
        flags |= Qt.WindowType.Window if parent is None else Qt.WindowType.Dialog
        super().__init__(parent, flags)
        self.setMouseTracking(True)
        self.title = title
        self.resizable = resizable
        self._icon = icon
        self._maximized = False
        self._normal_geometry = QRect()
        self.always_active = False      # paint the title bar navy even when not focused

        self.body = QWidget(self)
        self.body.setMouseTracking(True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(FRAME, FRAME + TITLE_H + 1, FRAME, FRAME)
        outer.setSpacing(0)
        outer.addWidget(self.body)

        self._buttons: list[CaptionButton] = []
        if resizable:
            self._min = CaptionButton("min", self)
            self._min.clicked.connect(self.showMinimized)
            self._max = CaptionButton("max", self)
            self._max.clicked.connect(self.toggle_maximized)
            self._buttons += [self._min, self._max]
        if closable:
            close = CaptionButton("close", self)
            close.clicked.connect(self.close)
            self._buttons.append(close)

    def set_title(self, title: str) -> None:
        self.title = title
        self.setWindowTitle(title)
        self.update()

    # --- maximize: done by hand, a frameless window would otherwise cover the taskbar -------

    @property
    def maximized(self) -> bool:
        return self._maximized

    def toggle_maximized(self) -> None:
        self.set_maximized(not self._maximized)

    def set_maximized(self, on: bool) -> None:
        if on == self._maximized:
            return
        if on:
            self._normal_geometry = self.geometry()
            screen = self.screen() or QApplication.primaryScreen()
            self._maximized = True
            self.setGeometry(screen.availableGeometry())
        else:
            self._maximized = False
            self.setGeometry(self._normal_geometry)
        self._max.kind = "restore" if on else "max"
        self._max.update()

    def normal_geometry(self) -> QRect:
        return self._normal_geometry if self._maximized else self.geometry()

    # --- painting -------------------------------------------------------------------------

    def resizeEvent(self, _event) -> None:
        x = self.width() - FRAME - 2
        for i, btn in enumerate(reversed(self._buttons)):
            x -= btn.width() + (2 if i == 1 else 0)   # Win95: a gap between close and the rest
            btn.move(x, FRAME + 2)

    def changeEvent(self, event) -> None:
        if event.type() == event.Type.ActivationChange:
            self.update()
        super().changeEvent(event)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        r = self.rect()
        p.fillRect(r, SILVER)
        raised(p, r.adjusted(0, 0, -1, -1))
        title = QRect(FRAME - 1, FRAME - 1, self.width() - 2 * FRAME + 2, TITLE_H)
        active = self.always_active or self.isActiveWindow()
        p.fillRect(title, NAVY if active else INACTIVE)
        text_left = 5
        if self._icon is not None:
            p.drawPixmap(title.left() + 2, title.top() + 1, self._icon)
            text_left = 21
        p.setFont(ui_font(bold=True))
        p.setPen(WHITE if active else SILVER)
        right = 4 + sum(b.width() for b in self._buttons) + 4
        p.drawText(title.adjusted(text_left, 0, -right, 0),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.title)
        p.end()

    # --- moving and resizing --------------------------------------------------------------

    def _edges(self, pos: QPoint) -> Qt.Edge:
        if not self.resizable or self._maximized:
            return Qt.Edge(0)
        grip = FRAME + 2
        edges = Qt.Edge(0)
        if pos.x() < grip:
            edges |= Qt.Edge.LeftEdge
        elif pos.x() >= self.width() - grip:
            edges |= Qt.Edge.RightEdge
        if pos.y() < grip:
            edges |= Qt.Edge.TopEdge
        elif pos.y() >= self.height() - grip:
            edges |= Qt.Edge.BottomEdge
        return edges

    def _cursor_for(self, edges: Qt.Edge) -> Qt.CursorShape:
        left_or_right = edges & (Qt.Edge.LeftEdge | Qt.Edge.RightEdge)
        top_or_bottom = edges & (Qt.Edge.TopEdge | Qt.Edge.BottomEdge)
        if left_or_right and top_or_bottom:
            main_diagonal = edges in (Qt.Edge.LeftEdge | Qt.Edge.TopEdge, Qt.Edge.RightEdge | Qt.Edge.BottomEdge)
            return Qt.CursorShape.SizeFDiagCursor if main_diagonal else Qt.CursorShape.SizeBDiagCursor
        if left_or_right:
            return Qt.CursorShape.SizeHorCursor
        if top_or_bottom:
            return Qt.CursorShape.SizeVerCursor
        return Qt.CursorShape.ArrowCursor

    def _in_title(self, pos: QPoint) -> bool:
        return FRAME <= pos.y() < FRAME + TITLE_H

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position().toPoint()
        edges = self._edges(pos)
        handle = self.windowHandle()
        if edges and handle is not None:
            handle.startSystemResize(edges)
        elif self._in_title(pos) and handle is not None and not self._maximized:
            handle.startSystemMove()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if self.resizable and self._in_title(event.position().toPoint()):
            self.toggle_maximized()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self.setCursor(self._cursor_for(self._edges(event.position().toPoint())))

    def closeEvent(self, event) -> None:
        self.close_requested.emit()
        super().closeEvent(event)


class ProgressBar(QWidget):
    """Win95 progress bar: navy blocks in a sunken well."""

    def __init__(self):
        super().__init__()
        self.value = 0.0
        self.setFixedHeight(20)

    def set_value(self, value: float) -> None:
        self.value = max(0.0, min(100.0, value))
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        r = self.rect()
        p.fillRect(r, SILVER)
        sunken(p, r.adjusted(0, 0, -1, -1))
        inner = r.adjusted(3, 3, -3, -3)
        filled = int(inner.width() * self.value / 100)
        x = inner.left()
        while x + 8 <= inner.left() + filled:
            p.fillRect(QRect(x, inner.top(), 8, inner.height()), NAVY)
            x += 10
        p.end()


def glyph(name: str) -> QPixmap:
    """16x16 pixel-art toolbar glyphs."""
    pm = QPixmap(16, 16)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(BLACK)
    if name == "play":
        p.drawPolygon(QPolygon([QPoint(5, 3), QPoint(5, 12), QPoint(10, 7)]))
        p.drawRect(5, 3, 1, 10)
    elif name == "pause":
        p.drawRect(4, 3, 3, 10)
        p.drawRect(9, 3, 3, 10)
    elif name == "step":
        p.drawPolygon(QPolygon([QPoint(3, 3), QPoint(3, 12), QPoint(8, 7)]))
        p.drawRect(3, 3, 1, 10)
        p.drawRect(10, 3, 2, 10)
    elif name == "seed":   # a die showing five
        p.setPen(BLACK)
        p.setBrush(WHITE)
        p.drawRect(2, 2, 11, 11)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(BLACK)
        for x, y in ((4, 4), (10, 4), (7, 7), (4, 10), (10, 10)):
            p.drawRect(x, y, 2, 2)
    elif name == "clear":   # a blank page with a red cross
        p.setPen(BLACK)
        p.setBrush(WHITE)
        p.drawRect(3, 1, 9, 13)
        p.setPen(QPen(QColor("#FF0000"), 2))
        p.drawLine(5, 5, 10, 10)
        p.drawLine(10, 5, 5, 10)
    elif name == "rules":   # a 3x3 neighborhood with the center lit
        p.setPen(BLACK)
        for i in range(3):
            for j in range(3):
                p.setBrush(QColor("#00FF00") if (i, j) == (1, 1) else WHITE)
                p.drawRect(1 + i * 5, 1 + j * 5, 4, 4)
    elif name == "fit":   # four corner marks
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(BLACK)
        for (x, y, dx, dy) in ((2, 2, 1, 1), (13, 2, -1, 1), (2, 13, 1, -1), (13, 13, -1, -1)):
            p.drawLine(x, y, x + 3 * dx, y)
            p.drawLine(x, y, x, y + 3 * dy)
        p.setBrush(QColor("#000080"))
        p.drawRect(6, 6, 3, 3)
    elif name == "open":   # a yellow folder
        p.setPen(BLACK)
        p.setBrush(QColor("#FFFF00"))
        p.drawPolygon(QPolygon([QPoint(1, 4), QPoint(5, 4), QPoint(6, 5), QPoint(13, 5), QPoint(13, 13),
                                QPoint(1, 13)]))
        p.setBrush(QColor("#808000"))
        p.drawPolygon(QPolygon([QPoint(1, 13), QPoint(4, 8), QPoint(15, 8), QPoint(13, 13)]))
    elif name == "patterns":   # a glider
        p.setPen(BLACK)
        p.setBrush(QColor("#00FFFF"))
        for x, y in ((6, 1), (11, 6), (1, 11), (6, 11), (11, 11)):
            p.drawRect(x, y, 3, 3)
    elif name in ("zoom_in", "zoom_out"):   # a magnifier
        p.setPen(QPen(BLACK, 1))
        p.setBrush(WHITE)
        p.drawEllipse(1, 1, 9, 9)
        p.setPen(QPen(BLACK, 2))
        p.drawLine(4, 6, 8, 6)
        if name == "zoom_in":
            p.drawLine(6, 4, 6, 8)
        p.drawLine(10, 10, 14, 14)
    p.end()
    return pm
