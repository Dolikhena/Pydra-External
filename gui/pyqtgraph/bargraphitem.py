"""This module contains a subclass for pyqtgraph's BarGraphItem and ErrorBarItem."""

from PyQt6.QtCore import Qt

from pyqtgraph import BarGraphItem, ErrorBarItem, PlotDataItem, QtCore


class UnclickableBarGraphItem(BarGraphItem):
    """Subclass of pyqtgraph's BarGraphItem, modified to support pen updates but not mouse events.

    This is used by the box plot (which is at least attended to by ClickableErrorBarItem) to avoid
    counter-productive signal pairs from being emitted during mouse clicks.
    """

    sigClicked = QtCore.Signal(object, object)

    @property
    def yData(self) -> float:
        """Match method from PlotDataItem."""
        return self.opts.get("y0")

    def setBrush(self, brush) -> None:
        """Match method from PlotDataItem. drawPicture() is not called since setPen is expected next."""
        self.opts["brush"] = brush
        # self.drawPicture()

    def setPen(self, pen) -> None:
        """Match method from PlotDataItem, calling drawPicture() to update plots with new colors."""
        self.opts["pen"] = pen
        self.drawPicture()


class ClickableBarGraphItem(UnclickableBarGraphItem):
    """Subclass of UnclickableBarGraphItem that supports mouse events."""

    sigClicked = QtCore.Signal(object, object)

    def mousePressEvent(self, event) -> None:
        """Emit mouse click signal when LMB is pressed."""
        if event.button() == Qt.MouseButton.LeftButton:
            return self.sigClicked.emit(self, event)
        super().mousePressEvent(event)


class ClickableErrorBarItem(ErrorBarItem):
    """Subclass of pyqtgraph's ErrorBarItem, modified to support mouse events and pen updates."""

    sigClicked = QtCore.Signal(object, object)

    def mouseClickEvent(self, event) -> None:
        """Select error bars (and box plots, by extension) using LMB.

        Because the error bars fully encapsulate their parent box plots, connecting and emitting
        signals on mouse click events would emit two duplicate events in rapid succession, which
        effectively blocks cursor interactions.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            self.sigClicked.emit(self, event)

    def setPen(self, pen) -> None:
        """Match method from PlotDataItem, calling drawPath() to update bars with new colors."""
        self.opts["pen"] = pen
        self.drawPath()


class OutlierDataItem(PlotDataItem):
    """Subclass of pyqtgraph's PlotDataItem. Unmodified, but easier to filter from legends."""
