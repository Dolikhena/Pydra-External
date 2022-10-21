"""This module contains a subclass for pyqtgraph's PlotWidget."""

from core.configuration import session, setting
from core.logger import get_logger
from gui.contextsignals import ContextSignal, MenuOption
from gui.plotobject import PlotObject
from gui.pyqtgraph.viewbox import ContextMenuViewBox
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor

from pyqtgraph import AxisItem, InfiniteLine, PlotDataItem, PlotWidget, SignalProxy, mkPen

logger = get_logger(__name__)


class ContextMenuPlotWidget(PlotWidget):
    """Subclass of pyqtgraph's PlotWidget, which uses custom ViewBox class."""

    main_window = None

    def __init__(self, parent, **kwargs) -> None:
        self.viewbox = ContextMenuViewBox(plot_widget=self)
        super().__init__(parent=parent, viewBox=self.viewbox, **kwargs)
        self.useOpenGL(setting("Plotting", "Renderer") == "OpenGL")

    def set_name(self, instance_name: str) -> None:
        """Provide a common name ('Line', 'Percentiles', etc.) to the PlotWidget and its viewbox.

        This handle is used to provide appropriate context menu options.
        """
        self.name: str = instance_name
        self.viewbox.set_name(instance_name)
        self.create_blank_axis("right")

        if self.name == "Experience":
            self.customize_experience_plot()

    def force_autorange(self) -> None:
        """Force the plot to use the autoranging function."""
        self.viewbox.setXRange(0, 1)
        self.viewbox.setYRange(0, 1)
        self.viewbox.autoRange(padding=0.1)

    def customize_experience_plot(self) -> None:
        """Modify the Experience plot to better match the intended format."""
        self.create_blank_axis("left")

        # Add a vertical infinite line to separate the latency and performance regions
        divider = InfiniteLine(pen=QColor("gray"), movable=False)
        self.viewbox.addItem(divider, ignoreBounds=True)

    def create_blank_axis(self, axis: str):
        """Create an invisible axis for padding the viewbox."""
        blank = mkPen(None)
        self.setAxisItems(
            axisItems={axis: AxisItem(axis, pen=blank, textPen=blank, showValues=False)}
        )

        axis = self.getAxis(axis)
        axis.style["tickAlpha"] = 0
        axis.setWidth(20)

    def show_crosshair(self) -> None:
        """Add two infinite lines which follow the coordinates of the cursor."""
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.vertical_line = InfiniteLine(pen="#4444ffaa")
        self.addItem(self.vertical_line, ignoreBounds=True)

        self.horizontal_line = InfiniteLine(angle=0, pen="#ff00ffaa")
        self.addItem(self.horizontal_line, ignoreBounds=True)

        # Config settings
        update_rate: int = int(setting("Crosshair", "CursorUpdateRate"))
        use_downsampling: bool = setting("Crosshair", "UseDownsampling") != "Disabled"

        # Condense many signals over a given time period into a single signal
        self.proxy = SignalProxy(
            self.scene().sigMouseMoved,
            rateLimit=update_rate,
            slot=self.update_cursor_position,
        )

        # Optionally subsample plotted curves to improve performance
        if use_downsampling:
            if setting("Crosshair", "UseDownsampling") == "Automatic":
                for curve in self.plotItem.curves:
                    curve.setDownsampling(auto=True)
            else:
                sample_rate: int = int(setting("Crosshair", "SampleRate"))
                for curve in self.plotItem.curves:
                    curve.setDownsampling(ds=sample_rate)

        self.cursor_visible = True

    def hide_crosshair(self) -> None:
        """Remove the cursor crosshairs from the plot."""
        self.removeItem(self.vertical_line)
        self.removeItem(self.horizontal_line)
        self.setCursor(
            Qt.CursorShape.BusyCursor if session("BusyCursor") else Qt.CursorShape.ArrowCursor
        )

        # Restore native sampling rate
        for curve in self.plotItem.curves:
            curve.setDownsampling(ds=1, auto=False)

        self.cursor_visible = False

    def redraw_crosshair(self) -> None:
        """Hide and show the crosshair if already visible. Used when changing config options from the GUI."""
        if hasattr(self, "cursor_visible") and self.cursor_visible:
            self.hide_crosshair()
            self.show_crosshair()

    def active_visible_crosshair(self, pos) -> bool:
        """Check for support and state of the crosshair cursors.

        Args:
            * pos: Current mouse cursor position (relative to the plot widget).

        Returns:
            * bool: True/false for whether the crosshair cursor is within the plot region.
        """
        return (
            hasattr(self, "cursor_visible")
            and self.cursor_visible
            and pos.x() < self.width()
            and pos.y() < self.height()
        )

    def dragging_plot(self) -> bool:
        """Return True if a plot is currently being dragged."""
        return hasattr(self, "dragged_plot") and self.dragged_plot is not None

    def drop_plot(self) -> None:
        """Update a dropped plot's time metrics, reset tracking variables, and re-enable context menus."""
        ContextSignal.emit(MenuOption.PlotDropped.value)
        self.toggle_mouse_interaction(True)

        # Reset vars for next LMB click
        self.cursor_drag_start = 0.0
        self.cursor_drag_stop = 0.0
        self.dragged_plot = None

    def cursor_coordinates(self) -> QPointF:
        """Translate cursor coordinates from absolute to relative position."""
        return self.viewbox.mapSceneToView(self.lastMousePos)

    def toggle_mouse_interaction(self, toggle: bool) -> None:
        """Temporarily suspend/resume mouse controls for the widget while/after dragging a plot."""
        self.viewbox.setMouseEnabled(x=toggle, y=toggle)

    def update_cursor_position(self, event) -> None:
        """Match the positions of the crosshairs to the current cursor position."""
        pos = event[0]

        if not self.active_visible_crosshair(pos):
            return

        cursor: QPointF = self.cursor_coordinates()
        x, y = cursor.x(), cursor.y()

        self.vertical_line.setPos(x)
        self.horizontal_line.setPos(y)

        if self.dragging_plot():
            self.cursor_drag_stop = x - self.cursor_drag_start
            self.cursor_drag_start = x

            self.dragged_plot.file.offset_time_axis(round(self.cursor_drag_stop, 9))
            ContextSignal.emit(MenuOption.PlotDragged.value)

    def leaveEvent(self, ev) -> None:
        """If the cursor leaves the plot region while dragging a curve, forcibly drop it.

        Args:
            * ev: Fired by pyqtgraph plot widget.
        """
        if self.dragging_plot():
            self.drop_plot()
            logger.info("Cursor left plot region while dragging - forcibly dropped curve")
        super().leaveEvent(ev)

    def mouseMoveEvent(self, ev) -> None:
        """Viewbox must be kept aware of cursor position for action shortcuts to work."""
        self.viewbox.cursor_position = self.viewbox.mapDeviceToView(ev.pos()).x()
        super().mouseMoveEvent(ev)

    def mousePressEvent(self, event) -> None:
        """Detect mouse clicks to determine if the selected plot is being dragged."""
        pos = event.pos()

        if self.active_visible_crosshair(pos):
            cursor: QPointF = self.cursor_coordinates()
            plot_items: list = [
                item for item in self.scene().items() if isinstance(item, PlotDataItem)
            ]

            hovered_curve = (
                PlotObject.get_by_curve(pdi)
                for pdi in plot_items
                if pdi.curve.mouseShape().contains(cursor)
                and PlotObject.get_by_curve(pdi) == PlotObject.get_selected()
            )

            if curve := (next(hovered_curve, None)):
                self.dragged_plot = curve
                self.cursor_drag_start = cursor.x()
                self.toggle_mouse_interaction(False)
                return super().mousePressEvent(event)

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        """Detect mouse button releases to determine when a dragged plot has been dropped.

        Args:
            * event: Fired by pyqtgraph plot widget.
        """
        if self.dragging_plot():
            self.drop_plot()

        super().mouseReleaseEvent(event)
