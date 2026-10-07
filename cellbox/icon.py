"""The app icon: a glider in a beveled Win95 box, drawn at any size."""

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap

from cellbox.palette import VGA

GLIDER = ((0, 1, "cyan"), (1, 2, "lime"), (2, 0, "yellow"), (2, 1, "white"), (2, 2, "white"))


def draw_icon(p: QPainter, size: int) -> None:
    s = size / 16   # designed on a 16x16 grid
    p.setPen(Qt.PenStyle.NoPen)
    box = QRectF(0, 0, size, size)
    p.fillRect(box, QColor("#C0C0C0"))
    edge = max(1.0, s)
    p.fillRect(QRectF(0, 0, size, edge), QColor("#FFFFFF"))
    p.fillRect(QRectF(0, 0, edge, size), QColor("#FFFFFF"))
    p.fillRect(QRectF(0, size - edge, size, edge), QColor("#000000"))
    p.fillRect(QRectF(size - edge, 0, edge, size), QColor("#000000"))
    well = QRectF(2 * s, 2 * s, 12 * s, 12 * s)
    p.fillRect(well, QColor("#000000"))
    cell = 3 * s
    for y, x, color in GLIDER:
        p.fillRect(QRectF(well.left() + 1.5 * s + x * cell, well.top() + 1.5 * s + y * cell,
                          cell - max(0.5, s * 0.5), cell - max(0.5, s * 0.5)), QColor(VGA[color]))


def icon_pixmap(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    draw_icon(p, size)
    p.end()
    return pm


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(icon_pixmap(size))
    return icon
