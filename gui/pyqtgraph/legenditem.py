"""This module contains a subclass for pyqtgraph's LegendItem."""

from typing import Optional

from core.configuration import session
from core.signaller import IntSignaller, StringSignaller, TupleSignaller
from core.utilities import color_picker
from gui.contextsignals import ContextSignal, MenuOption
from gui.plotobject import PlotObject
from gui.pyqtgraph.itemsample import SquareItemSample
from gui.styles import current_stylesheet
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu

from pyqtgraph import LabelItem, LegendItem, mkBrush, mkPen


class ClickableLabelItem(LabelItem):
    """Subclass of pyqtgraph's LabelItem, for displaying subclassed ItemSample objects."""

    def __init__(self, *args, **kwargs) -> None:
        self.parent = kwargs["parent"]
        self.curve = kwargs["curve"]
        self.plot_obj = kwargs["plot_obj"]
        super().__init__(*args, **kwargs)

    def mousePressEvent(self, event) -> None:
        """Pass the LMB click event up to the owning SquareLegendItem."""
        self.parent.label_clicked(event, self.curve)
        # Not calling super() method prevents selecting curves behind the legend

    def hoverEvent(self, event) -> None:
        """Refresh tooltip and legend text colors when hovering over a legend item."""
        if event.enter:
            self.setToolTip(self.plot_obj.tooltip())
            self.apply_hover_styling()
            return self.parent.hoverEvent(event)
        elif event.exit:
            self.setToolTip("")
            return self.remove_hover_styling()

    def apply_hover_styling(self) -> None:
        """Highlight the text of the hovered legend item."""
        if not self.text.startswith("<span style='color:"):
            self.setText(
                f"<span style='color:{self.parent._hovered_text_color};'>{self.text}</span>"
            )

    def remove_hover_styling(self) -> None:
        """Strip highlight styling from the hovered legend item."""
        if not self.parent._menu_open and self.text.startswith("<span style='color:"):
            self.setText(self.text[26:-7])


class SquareLegendItem(LegendItem):
    """Subclass of pyqtgraph's LegendItem, for displaying subclassed ItemSample objects."""

    _context_menu: QMenu = None
    _hovered_border_color: str = ""
    _hovered_text_color: str = ""
    _instances: list = []
    _menu_open: bool = False
    _menu_pos = None
    _moved: bool = False
    _selected_file = None

    clicked: TupleSignaller = TupleSignaller()
    dragged: IntSignaller = IntSignaller()
    time_reset: IntSignaller = IntSignaller()
    view_file: StringSignaller = StringSignaller()
    view_properties: StringSignaller = StringSignaller()

    @classmethod
    def update_all(cls) -> None:
        """Repaint each legend's samples in response to file selection."""
        for instance in cls._instances:
            instance.updateSize()

    @classmethod
    def clear_all(cls) -> None:
        """Override method to handle SquareItemSample objects."""
        for instance in cls._instances:
            instance.clear()

    @classmethod
    def style_backgrounds(cls) -> None:
        """Change background and border colors to match the current stylesheet."""
        for instance in cls._instances:
            instance.match_stylesheet()

    @classmethod
    def reorder_legend_item(cls, index: int = 0, relative: bool = False) -> None:
        selection = SquareLegendItem._selected_file or PlotObject.get_by_path(
            session("SelectedFilePath")
        )
        PlotObject.reposition_legend(selection, index, relative)
        ContextSignal.emit(MenuOption.ReorderLegend.value)

    @classmethod
    def create_menu(cls) -> QMenu:
        """Define the layout and actions for the context menu used by legend items.

        This is defined as a class method to avoid needless re-creations as new legend items are
        created.
        """

        context_menu: QMenu = QMenu()

        cls.select_target_file: QAction = QAction("Select plot", context_menu)
        cls.select_target_file.triggered.connect(cls.select_file)
        cls.raise_color_picker = QAction("Change plot color", context_menu)
        cls.raise_color_picker.triggered.connect(cls.set_plot_color)

        cls.move_to_top: QAction = QAction("Move to top", context_menu)
        cls.move_to_top.triggered.connect(cls.reorder_legend_item)
        cls.move_up: QAction = QAction("Move up", context_menu)
        cls.move_up.triggered.connect(lambda: cls.reorder_legend_item(-1, True))
        cls.move_down: QAction = QAction("Move down", context_menu)
        cls.move_down.triggered.connect(lambda: cls.reorder_legend_item(1, True))
        cls.move_to_bottom: QAction = QAction("Move to bottom", context_menu)
        cls.move_to_bottom.triggered.connect(lambda: cls.reorder_legend_item(-1))

        cls.reset_time_offset = QAction("Reset time offset", context_menu)
        cls.reset_time_offset.triggered.connect(cls.reset_file_times)

        cls.clear_file = QAction("Clear file from plot", context_menu)
        cls.clear_file.triggered.connect(cls.clear_selected_file)

        cls.view_in_browser = QAction("View in file browser", context_menu)
        cls.view_in_browser.triggered.connect(cls.view_file_in_browser)
        cls.view_file_properties = QAction("Properties", context_menu)
        cls.view_file_properties.triggered.connect(cls.show_properties)

        # Add menu items in the order they'll appear
        context_menu.addAction(cls.select_target_file)
        context_menu.addAction(cls.raise_color_picker)
        context_menu.addSeparator()
        context_menu.addAction(cls.move_to_top)
        context_menu.addAction(cls.move_up)
        context_menu.addAction(cls.move_down)
        context_menu.addAction(cls.move_to_bottom)
        context_menu.addSeparator()
        context_menu.addAction(cls.reset_time_offset)
        context_menu.addSeparator()
        context_menu.addAction(cls.clear_file)
        context_menu.addSeparator()
        context_menu.addAction(cls.view_in_browser)
        context_menu.addAction(cls.view_file_properties)

        context_menu.setStyleSheet(current_stylesheet())
        return context_menu

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(horSpacing=25, verSpacing=2, *args, **kwargs)
        SquareLegendItem._instances += [self]
        self.sampleType = SquareItemSample

        if SquareLegendItem._context_menu is None:
            SquareLegendItem.context_menu = SquareLegendItem.create_menu()

    def colorize(self, label=None) -> None:
        """Colorize the legend items."""
        for _, item in self.items:
            if item.text.startswith("<span style='color"):
                item.setText(item.text[26:-7])

        if label:
            label.setText(f"<span style='color:#f00;'>{label.text}</span>")

    def label_by_object(self, plot_obj) -> object:
        for row in range(len(self.items)):
            if (label := self.items[row][1]).plot_obj == plot_obj:
                return label

    def reorder_legend_items(self) -> None:
        """Rearrange the position of legend items to match the current ordering."""
        sample, label, shown = None, None, None
        samples_and_labels: dict = {
            self.items[row][1].plot_obj: self.items[row] for row in range(len(self.items))
        }

        # Add items according to their position
        while samples_and_labels:
            shown = (item for item in PlotObject.legend_order if item in samples_and_labels)
            for item in shown:
                sample, label = samples_and_labels.pop(item)
                self._addItemToLayout(sample, label)

                # Somewhat excessive to call every iteration, but it's best for resizing
                # the legend bounding box after removing legends with very long names.
                self.updateSize()

    def toggle(self) -> None:
        """Toggle the visibility of the legend."""
        self.setVisible(not self.isVisible())

    def reset_position(self) -> None:
        """Shift the legend position left and down for better composition."""
        self.anchor((1, 0), (1, 0), (-5, 4))

        if SquareLegendItem._moved:
            SquareLegendItem._moved = False

    def match_stylesheet(self, alpha: str = "dd") -> None:
        """Style UI elements to match the current stylesheet."""
        dark_mode: bool = session("DarkMode")
        self._hovered_border_color = f"#{'666666' if dark_mode else 'bbbbbb'}"
        self._hovered_text_color = f"#{'fff' if dark_mode else '000'}"
        self.setBrush(mkBrush(f"#{'252525' if dark_mode else 'f4f4f4'}{alpha}"))

    def label_clicked(self, event, curve) -> None:
        """Emit a signal to select the capture file corresponding to the clicked label."""
        # Prevent this context menu from opening if the cursor has moved out of the legend
        if not self.isUnderMouse():
            return

        if event.button() == Qt.MouseButton.LeftButton:
            return SquareLegendItem.clicked.signal.emit((curve, self.set_selected_file))
        if event.button() == Qt.MouseButton.RightButton:
            SquareLegendItem._menu_pos = event.screenPos()
            return SquareLegendItem.clicked.signal.emit((curve, self.raise_context_menu))

    def addItem(self, item, name, plot_obj: PlotObject) -> None:
        """Override default method to use clickable label class associated with a PlotObject.

        Legend items are added at the end of the MainWindow plotting function by calling
        reorder_legend_items so that they are kept in proper order.
        """
        label = ClickableLabelItem(
            name,
            parent=self,
            plot_obj=plot_obj,
            curve=item,
            color=self.opts["labelTextColor"],
            justify="left",
            size=self.opts["labelTextSize"],
        )
        sample = item if isinstance(item, self.sampleType) else self.sampleType(item)
        self.items.append((sample, label))

    @staticmethod
    def select_file() -> None:
        """Highlight a file's plots, identical to clicking a plot from the pyqtgraph widgets."""
        PlotObject.select_by_path(SquareLegendItem._selected_file.file.path)

    @staticmethod
    def set_plot_color() -> None:
        """Raise a color picker dialog window for changing the selected file's pen color."""
        plot_obj: PlotObject = SquareLegendItem._selected_file
        new_color: Optional[tuple] = color_picker(plot_obj.pen)

        if new_color is not None:
            plot_obj.pen = new_color
            PlotObject.update_object_pen(plot_obj)

    @staticmethod
    def reset_file_times() -> None:
        """Remove offsets and trimming from all plotted files."""
        SquareLegendItem._selected_file.file.reset_time_axis()
        SquareLegendItem.time_reset.signal.emit(0)

    @staticmethod
    def clear_selected_file() -> None:
        """Clear the selected file from all plots.

        If the user has right-clicked on a legend item that is not the selected file, this will select
        the item (through PlotObject), clear it, then re-select the file that was previously selected.
        """
        hovered_legend_item: Optional[PlotObject] = SquareLegendItem._selected_file
        selected_plot_obj: PlotObject = PlotObject.get_selected()

        if hovered_legend_item != selected_plot_obj:
            PlotObject.select_by_path(hovered_legend_item.file.path)
            ContextSignal.emit(MenuOption.ClearFile.value)

            if selected_plot_obj:  # Reselect previous file
                PlotObject.select_by_path(selected_plot_obj.file.path)
        else:
            ContextSignal.emit(MenuOption.ClearFile.value)

    @staticmethod
    def view_file_in_browser() -> None:
        """Load this file into the file browser and switch tab view."""
        SquareLegendItem.view_file.signal.emit(SquareLegendItem._selected_file.file.path)

    @staticmethod
    def show_properties() -> None:
        """Raise a dialog window for viewing or changing a file's properties."""
        SquareLegendItem.view_properties.signal.emit(SquareLegendItem._selected_file.file.path)

    def mouseDragEvent(self, event) -> None:
        """Use drag events to show the 'Reset Legend Position' button."""
        if not SquareLegendItem._moved:
            SquareLegendItem.dragged.signal.emit(1)
            SquareLegendItem._moved = True
        return super().mouseDragEvent(event)

    def hoverEvent(self, event) -> None:
        """Highlight the legend border when the user hovers over."""
        if event.enter:
            self.setPen(mkPen(self._hovered_border_color))
            self.setToolTip("Click and drag to move the legend.")
        elif event.exit:
            self.setPen(mkPen(None))
        super().hoverEvent(event)

    def set_selected_file(self, legend_item: PlotObject) -> None:
        """Select a file when a LMB click occurs within the legend."""
        SquareLegendItem._selected_file = legend_item
        PlotObject.select_by_path(legend_item.file.path)

    def raise_context_menu(self, plot_obj: PlotObject) -> None:
        """Raise the context menu at the cursor when user right-clicks in a pyqtgraph region."""
        SquareLegendItem._selected_file = plot_obj
        SquareLegendItem.context_menu.setStyleSheet(current_stylesheet())

        # Preserve the label highlight while the context menu is opened and remove it once closed
        self._menu_open = True
        SquareLegendItem.context_menu.exec(
            QPoint(SquareLegendItem._menu_pos.x(), SquareLegendItem._menu_pos.y())
        )
        self._menu_open = False
        self.label_by_object(plot_obj).remove_hover_styling()
