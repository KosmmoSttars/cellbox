"""The field view: crisp integer zoom, drag to pan, wraps around like the torus it shows.

Works in device pixels so cells stay square and even at 125% or 150% Windows scaling.
"""

import math

from PyQt6.QtCore import QPointF, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QMouseEvent, QPainter, QWheelEvent
from PyQt6.QtWidgets import QWidget

from cellbox.engine import Field

MIN_ZOOM = 1
MAX_ZOOM = 16
WORKSPACE = QColor("#808080")   # Win95 "application workspace" gray around a small field


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

    def __init__(self, field: Field):
        super().__init__()
        self.field = field
        self.zoom = 3
        self.offset = QPointF(0, 0)   # cell at the top-left corner of a panned (wider than view) axis
        self.table: list[int] = []
        self._drag_from: QPointF | None = None
        self.setMinimumSize(160, 120)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def set_color_table(self, table: list[int]) -> None:
        self.table = table
        self.update()

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
        p.end()

    # --- panning and zooming with the mouse -----------------------------------------------

    def wheelEvent(self, event: QWheelEvent) -> None:
        steps = event.angleDelta().y() // 120
        zoom = self.zoom
        for _ in range(abs(steps)):
            zoom = max(MIN_ZOOM, min(MAX_ZOOM, self._next_zoom(zoom, steps)))
        self.set_zoom(zoom, event.position() * self._dpr())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self._drag_from = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_from is None:
            return
        delta = (event.position() - self._drag_from) * self._dpr()
        self._drag_from = event.position()
        self.offset -= QPointF(delta.x() / self.zoom, delta.y() / self.zoom)
        self._wrap()
        self.update()

    def mouseReleaseEvent(self, _event: QMouseEvent) -> None:
        self._drag_from = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseDoubleClickEvent(self, _event: QMouseEvent) -> None:
        self.fit()
