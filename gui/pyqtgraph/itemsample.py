"""This module contains a subclass for pyqtgraph's ItemSample."""

from core.configuration import setting
from PyQt6.QtCore import QRect, QRectF, Qt

from pyqtgraph import ItemSample, mkBrush
from pyqtgraph.icons import invisibleEye


class ResizeableSample(ItemSample):
    """Subclass of pyqtgraph's ItemSample that allows for resizeable bounding rect."""

    def boundingRect(self, as_qrect: bool = False) -> QRectF:
        font_size: int = int(setting("Plotting", "LegendItemFontSize"))
        x: int = 19 - font_size  # 5 pixel margin (given a max font size of 24)
        y: int = int((font_size / 2) + 3.5)  # Rounding helps with centering at smaller sizes

        if as_qrect:
            return QRect(x, y, font_size, font_size)
        return QRectF(x, y, font_size, font_size)


class SquareItemSample(ResizeableSample):
    """Subclass of pyqtgraph's ItemSample for displaying square plot samples in the legend."""

    def __init__(self, item, *args, **kwargs) -> None:
        super().__init__(self, *args, **kwargs)
        self.item = item

    def paint(self, painter, *args) -> None:
        """Draw a square sample for each plot regardless of object type."""
        # Change legend sample if curve is hidden from view
        visible = self.item.isVisible()
        if not visible:
            font_size: int = int(setting("Plotting", "LegendItemFontSize"))
            icon = invisibleEye.qicon
            painter.drawPixmap(self.boundingRect(as_qrect=True), icon.pixmap(font_size, font_size))
            return

        # Enhancement: coordinate border color with CSS
        pen = (
            self.item.opts["pen"]
            if "symbol" not in self.item.opts or self.item.opts["symbol"] is None
            else self.item.opts["symbolPen"]
        )
        if pen is not None:
            painter.setBrush(mkBrush(pen) if isinstance(pen, tuple) else mkBrush(pen.color()))
        painter.drawRect(self.boundingRect())

    def mouseClickEvent(self, event) -> None:
        """Only left mouse button clicks will hide plot items."""
        if event.button() == Qt.MouseButton.LeftButton:
            return super().mouseClickEvent(event)
