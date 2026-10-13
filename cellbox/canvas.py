"""The field view: crisp integer zoom, drag to pan, wraps around like the torus it shows.

While a pattern is being placed, a see-through copy of it follows the mouse: a click (a press and release
without dragging) drops it there, the right button turns it.

Works in device pixels so cells stay square and even at 125% or 150% Windows scaling.
"""

import math

import numpy as np
from PyQt6.QtCore import QPointF, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPen, QWheelEvent
from PyQt6.QtWidgets import QWidget

from cellbox.engine import Field
from cellbox.patterns import Pattern

MIN_ZOOM = 1
MAX_ZOOM = 16
WORKSPACE = QColor("#808080")   # Win95 "application workspace" gray around a small field
GHOST_ALPHA = 150
CLICK_SLOP = 4                  # pixels the mouse may travel between press and release and still click


def _segments(view: int, n: int, zoom: int, offset: float) -> list[tuple[int, int, int]]:
    """Along one axis: (first cell, cell count, device pixel position) runs that cover the view.

    A field narrower than the view is centered; a wider one is panned by offset (in cells) and
    wraps around.
    """
    if n * zoom <= view:
        return [(0, n, (view - n * zoom) // 2)]
    px = round(offset * zoom) % (n * zoom)
    cell, pos = divmod(px, zoom)
    pos = -pos
    runs = []
    while pos < view:
        count = min(n - cell, math.ceil((view - pos) / zoom))
        runs.append((cell, count, pos))
        pos += count * zoom
        cell = 0
    return runs


class FieldView(QWidget):
    view_changed = pyqtSignal()
    stamp_requested = pyqtSignal(int, int)   # top-left cell (row, column) to drop the pattern at

    def __init__(self, field: Field):
        super().__init__()
        self.field = field
        self.zoom = 3
        self.offset = QPointF(0, 0)   # cell at the top-left corner of a panned (wider than view) axis
        self.table: list[int] = []
        self.pattern: Pattern | None = None
        self._ghost: QImage | None = None
        self._hover: QPointF | None = None    # mouse position in device pixels
        self._drag_from: QPointF | None = None
        self._press_at: QPointF | None = None
        self._dragged = False
        self.setMinimumSize(160, 120)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMouseTracking(True)
        self._idle_cursor()

    def set_color_table(self, table: list[int]) -> None:
        self.table = table
        self._ghost = self._ghost_image() if self.pattern else None
        self.update()

    def _idle_cursor(self) -> None:
        self.setCursor(Qt.CursorShape.CrossCursor if self.pattern else Qt.CursorShape.OpenHandCursor)

    # --- geometry in device pixels ----------------------------------------------------------

    def _dpr(self) -> float:
        return self.devicePixelRatioF()

    def _view_size(self) -> tuple[int, int]:
        dpr = self._dpr()
        return round(self.width() * dpr), round(self.height() * dpr)

    def _wrap(self) -> None:
        n = self.field.size
        self.offset = QPointF(self.offset.x() % n, self.offset.y() % n)

    def _cell_at(self, anchor: float, view: int, offset: float) -> float:
        """The cell coordinate under a device pixel along one axis, for the current zoom."""
        n, z = self.field.size, self.zoom
        if n * z <= view:
            return (anchor - (view - n * z) // 2) / z
        return offset + anchor / z

    def _cell_px(self, cell: int, view: int, offset: float) -> int:
        """Device pixel of a cell's leading edge along one axis, within one torus period of the view."""
        n, z = self.field.size, self.zoom
        if n * z <= view:
            return (view - n * z) // 2 + cell * z
        return round((cell - offset) * z) % (n * z)

    def set_zoom(self, zoom: int, anchor: QPointF | None = None) -> None:
        """Changes the zoom, keeping the cell under anchor (device pixels) in place."""
        zoom = max(MIN_ZOOM, min(MAX_ZOOM, zoom))
        if zoom == self.zoom:
            return
        w, h = self._view_size()
        if anchor is None:
            anchor = QPointF(w / 2, h / 2)
        cx = self._cell_at(anchor.x(), w, self.offset.x())
        cy = self._cell_at(anchor.y(), h, self.offset.y())
        self.zoom = zoom
        self.offset = QPointF(cx - anchor.x() / zoom, cy - anchor.y() / zoom)
        self._wrap()
        self.update()
        self.view_changed.emit()

    @staticmethod
    def _next_zoom(zoom: int, direction: int) -> int:
        """1, 2, 3, 4, then doubling: 8, 16."""
        if direction > 0:
            return zoom + 1 if zoom < 4 else zoom * 2
        return zoom - 1 if zoom <= 4 else zoom // 2

    def zoom_in(self) -> None:
        self.set_zoom(self._next_zoom(self.zoom, 1))

    def zoom_out(self) -> None:
        self.set_zoom(self._next_zoom(self.zoom, -1))

    def fit(self) -> None:
        """The biggest zoom that shows the whole field, centered (1x if even that is too big)."""
        n = self.field.size
        w, h = self._view_size()
        self.zoom = max(MIN_ZOOM, min(MAX_ZOOM, min(w, h) // n))
        self.offset = QPointF((n - w / self.zoom) / 2, (n - h / self.zoom) / 2)
        self._wrap()
        self.update()
        self.view_changed.emit()

    def show_area(self, row: float, col: float, height: int, width: int) -> None:
        """Zooms to show about this many cells around (row, col), centered on it."""
        w, h = self._view_size()
        zoom = min(w / max(width, 1), h / max(height, 1))
        steps = [z for z in (1, 2, 3, 4, 8, 16) if z <= zoom]
        self.zoom = steps[-1] if steps else MIN_ZOOM
        self.offset = QPointF(col - w / self.zoom / 2, row - h / self.zoom / 2)
        self._wrap()
        self.update()
        self.view_changed.emit()

    # --- placing patterns -------------------------------------------------------------------

    def set_pattern(self, pattern: Pattern | None) -> None:
        self.pattern = pattern
        self._ghost = self._ghost_image() if pattern else None
        self._idle_cursor()
        self.update()

    def rotate_pattern(self) -> None:
        if self.pattern is not None:
            self.set_pattern(self.pattern.rotated())

    def _ghost_image(self) -> QImage:
        cells = self.pattern.cells
        if cells.dtype != np.uint8:
            cells = np.rint(cells * 255).astype(np.uint8)
        cells = np.ascontiguousarray(cells)
        h, w = cells.shape
        img = QImage(cells.data, w, h, w, QImage.Format.Format_Indexed8)
        table = self.table or [0xFFFFFFFF] * 256
        img.setColorTable([0] + [(c & 0x00FFFFFF) | (GHOST_ALPHA << 24) for c in table[1:]])
        return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)   # copies the numpy data

    def _ghost_origin(self) -> tuple[int, int] | None:
        """Top-left cell of the ghost: the pattern is held by its middle."""
        if self.pattern is None or self._hover is None:
            return None
        w, h = self._view_size()
        cx = math.floor(self._cell_at(self._hover.x(), w, self.offset.x()))
        cy = math.floor(self._cell_at(self._hover.y(), h, self.offset.y()))
        n = self.field.size
        return (cy - self.pattern.height // 2) % n, (cx - self.pattern.width // 2) % n

    # --- painting ---------------------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        dpr = self._dpr()
        p.scale(1 / dpr, 1 / dpr)
        w, h = self._view_size()
        p.fillRect(QRect(0, 0, w, h), WORKSPACE)

        cells = self.field.display()
        n = self.field.size
        img = QImage(cells.data, n, n, n, QImage.Format.Format_Indexed8)
        img.setColorTable(self.table)
        z = self.zoom
        for sx, cw, dx in _segments(w, n, z, self.offset.x()):
            for sy, ch, dy in _segments(h, n, z, self.offset.y()):
                p.drawImage(QRect(dx, dy, cw * z, ch * z), img, QRect(sx, sy, cw, ch))
        self._paint_ghost(p, w, h)
        p.end()

    def _paint_ghost(self, p: QPainter, w: int, h: int) -> None:
        origin = self._ghost_origin()
        if origin is None or self._ghost is None:
            return
        n, z = self.field.size, self.zoom
        wrap = n * z
        gy = self._cell_px(origin[0], h, self.offset.y())
        gx = self._cell_px(origin[1], w, self.offset.x())
        gw, gh = self.pattern.width * z, self.pattern.height * z
        # a field smaller than the view: clip to it, the part past its edge shows up on the other side
        clip = QRect(0, 0, w, h)
        if wrap <= w:
            clip.setLeft((w - wrap) // 2)
            clip.setWidth(wrap)
        if wrap <= h:
            clip.setTop((h - wrap) // 2)
            clip.setHeight(wrap)
        p.save()
        p.setClipRect(clip)
        p.setPen(QPen(QColor("#FFFFFF"), 1, Qt.PenStyle.DotLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for ox in (0, -wrap):
            for oy in (0, -wrap):
                rect = QRect(gx + ox, gy + oy, gw, gh)
                if rect.intersects(clip):
                    p.drawImage(rect, self._ghost)
                    p.drawRect(rect.adjusted(0, 0, -1, -1))
        p.restore()

    # --- mouse: pan, zoom, place ------------------------------------------------------------

    def wheelEvent(self, event: QWheelEvent) -> None:
        steps = event.angleDelta().y() // 120
        zoom = self.zoom
        for _ in range(abs(steps)):
            zoom = max(MIN_ZOOM, min(MAX_ZOOM, self._next_zoom(zoom, steps)))
        self.set_zoom(zoom, event.position() * self._dpr())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton and self.pattern is not None:
            self.rotate_pattern()
        elif event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self._drag_from = self._press_at = event.position()
            self._dragged = False

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self._hover = event.position() * self._dpr()
        if self._drag_from is None:
            if self.pattern is not None:
                self.update()
            return
        if not self._dragged:
            if (event.position() - self._press_at).manhattanLength() < CLICK_SLOP:
                return
            self._dragged = True
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        delta = (event.position() - self._drag_from) * self._dpr()
        self._drag_from = event.position()
        self.offset -= QPointF(delta.x() / self.zoom, delta.y() / self.zoom)
        self._wrap()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        clicked = self._drag_from is not None and not self._dragged
        self._drag_from = None
        self._dragged = False
        self._idle_cursor()
        if clicked and event.button() == Qt.MouseButton.LeftButton:
            origin = self._ghost_origin()
            if origin is not None:
                self.stamp_requested.emit(*origin)

    def leaveEvent(self, _event) -> None:
        self._hover = None
        if self.pattern is not None:
            self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if self.pattern is None:
            self.fit()
        else:   # while placing, a quick second click places another copy
            self.mousePressEvent(event)
