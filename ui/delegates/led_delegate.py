from __future__ import annotations

from PyQt5.QtCore import Qt, QRect, QSize
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import QStyledItemDelegate


class LedBarDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index) -> QSize:
        return QSize(72, 22)

    def paint(self, painter: QPainter, option, index) -> None:
        raw = index.data(Qt.UserRole + 1)
        if not isinstance(raw, tuple) or len(raw) != 4:
            super().paint(painter, option, index)
            return

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect: QRect = option.rect
        painter.fillRect(rect, option.palette.base())

        led_size = 10
        gap = 6
        total_width = (led_size * 4) + (gap * 3)
        start_x = rect.x() + max(4, (rect.width() - total_width) // 2)
        y = rect.y() + max(4, (rect.height() - led_size) // 2)

        for idx, value in enumerate(raw):
            x = start_x + idx * (led_size + gap)
            color = QColor("#21c55d") if bool(value) else QColor("#d1d5db")
            painter.setBrush(color)
            painter.setPen(QPen(QColor("#6b7280")))
            painter.drawEllipse(x, y, led_size, led_size)

        painter.restore()