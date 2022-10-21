"""This module contains a subclass for pyqtgraph's ViewBox."""

from core.configuration import session, set_session_value, setting_bool, setting_exists
from core.exporter import write_image
from core.signaller import IntSignaller
from core.utilities import Tab, color_picker
from gui.contextsignals import ContextSignal, MenuOption
from gui.plotobject import PlotObject
from gui.pyqtgraph.legenditem import SquareLegendItem
from gui.styles import current_stylesheet
from PyQt6.QtCore import QPoint, Qt, pyqtSlot
from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtWidgets import QMenu

from pyqtgraph import ViewBox
from pyqtgraph.exporters import ImageExporter


class ContextMenuViewBox(ViewBox):
    """Subclass of pyqtgraph's ViewBox, modified to support custom context menus."""

    lmb_mode_changed: IntSignaller = IntSignaller()

    def __init__(self, plot_widget, *args) -> None:
        super(ContextMenuViewBox, self).__init__(*args)
        self.parent = plot_widget

        # Add subclassed LegendItem
        self.legend = SquareLegendItem(offset=(0, 1))
        self.legend.setParentItem(self)
        self.legend.reset_position()

        # Save cursor coordinates where context menu was opened
        self.cursor_position: float = 0

        # Connect to parent class's Qt signal to update each ViewBox's context menu and modes
        ContextMenuViewBox.lmb_mode_changed.signal.connect(self.set_lmb_mode)

    def set_name(self, instance_name: str) -> None:
        """Receive a common name from the parent PlotWidget for identification."""
        self.name = instance_name
        self.context_menu: QMenu = self.create_menu()

        # Hide the legend if this plot allows it
        if setting_exists(self.name, "HideLegend") and setting_bool(self.name, "HideLegend"):
            self.legend.toggle()

    def item_belongs_to_plot(self, item) -> bool:
        """Check that an object is the correct type to receive legend item."""
        return hasattr(self, "legend") and item.__class__.__name__ in {
            "PlotDataItem",
            "UnclickableBarGraphItem",  # Box plot
            "ClickableBarGraphItem",  # Experience plot
        }

    def addItem(self, item, **kwargs) -> None:
        """Override definition to customize label text."""
        if self.item_belongs_to_plot(item):
            # item.setZValue(len(self.addedItems))
            plot_obj = PlotObject.get_by_curve(item)

            legend_name: str = plot_obj.formatted_legend()
            if self.name == "Scatter" and session("ShowRSquaredValue"):
                legend_name += plot_obj.r_squared

            self.legend.addItem(item, legend_name, plot_obj)
        super().addItem(item, **kwargs)

    def update_label(self, curve, legend_name) -> None:
        """Refresh a legend item's text in response to a new format translation."""
        if label := self.legend.getLabel(curve):
            label.setText(legend_name)

    def removeItem(self, item, **kwargs) -> None:
        """Override definition to remove legend items when the viewbox is being cleared."""
        if self.item_belongs_to_plot(item):
            self.legend.removeItem(item)
        super().removeItem(item, **kwargs)

    def mouseClickEvent(self, ev):
        """Intercept right mouse button clicks to simplify the user experience.

        Right-clicking on a plot will attempt to select a file beneath the cursor, which saves the user
        from having to left-click on a plot before right-clicking to modify it.

        This does not work as well for scatter-based plots since the "shape" of the curve is generally
        very messy due to unordered data, meaning more variable data produces a larger point cloud, so
        choosing which curve "contains" the cursor is effectively meaningless.
        """
        if ev.button() == Qt.MouseButton.RightButton and not session("SelectedFilePath"):
            cursor = self.mapToView(ev.pos())
            curves: list = [item for item in self.addedItems if self.item_belongs_to_plot(item)]

            for item in curves:
                beneath_cursor = (
                    # item.scatter.shape().contains(cursor)
                    # if hasattr(item, "scatter") else
                    item.curve.mouseShape().contains(cursor)
                    if hasattr(item, "curve")
                    else item.isUnderMouse()
                )

                if beneath_cursor:
                    plot_obj = PlotObject.get_by_curve(item)
                    PlotObject.select_by_path(plot_obj.file.path)
                    self.parent.main_window.curve_was_clicked()
        return super().mouseClickEvent(ev)

    def raiseContextMenu(self, event) -> None:
        """Raise the context menu at the cursor when user right-clicks in a pyqtgraph region."""
        menu = self.getMenu()
        absolute_pos = event.screenPos()
        self.cursor_position = self.mapToView(event.pos()).x()

        menu.popup(QPoint(int(absolute_pos.x()), int(absolute_pos.y())))

    def create_menu(self) -> QMenu:
        """Define the layout and actions for each ViewBox's context menu.

        This menu is created after the parent widget has passed its name from the main window,
        which allows finer control over what items are enabled or visible.
        """
        context_menu: QMenu = QMenu()
        is_line_plot_vb: bool = self.name == "Line"
        is_scatter_plot_vb: bool = self.name == "Scatter"
        is_box_plot_vb: bool = self.name == "Box"
        is_experience_plot_vb: bool = self.name == "Experience"
        is_bar_plot_vb: bool = is_box_plot_vb or is_experience_plot_vb

        # Control group for selected plot
        self.selected_plot = QMenu("Selected plot", parent=context_menu)
        self.selected_plot_group = QActionGroup(self)

        self.raise_color_picker = QAction("Change plot color", context_menu)
        self.raise_color_picker.triggered.connect(self.set_plot_color)
        self.raise_color_picker.setActionGroup(self.selected_plot_group)
        self.selected_plot.addAction(self.raise_color_picker)

        self.selected_plot.addSection("Time options")

        self.zero_selected_axis = QAction("Start time axis at zero", context_menu)
        self.zero_selected_axis.triggered.connect(lambda: self.zero_times(False))
        self.zero_selected_axis.setActionGroup(self.selected_plot_group)
        self.zero_selected_axis.setVisible(is_line_plot_vb)
        self.selected_plot.addAction(self.zero_selected_axis)

        self.ignore_before_cursor = QAction("Trim time before cursor", context_menu)
        self.ignore_before_cursor.triggered.connect(lambda: self.trim_plots(False, "Before"))
        self.ignore_before_cursor.setActionGroup(self.selected_plot_group)
        self.ignore_before_cursor.setVisible(is_line_plot_vb)
        self.selected_plot.addAction(self.ignore_before_cursor)

        self.ignore_after_cursor = QAction("Trim time after cursor", context_menu)
        self.ignore_after_cursor.triggered.connect(lambda: self.trim_plots(False, "After"))
        self.ignore_after_cursor.setActionGroup(self.selected_plot_group)
        self.ignore_after_cursor.setVisible(is_line_plot_vb)
        self.selected_plot.addAction(self.ignore_after_cursor)

        self.selected_plot.addSection("Ordering options")

        self.move_to_top = QAction("Move to top", context_menu)
        self.move_to_top.triggered.connect(self.reorder_plots)
        self.move_to_top.setActionGroup(self.selected_plot_group)
        self.move_to_top.setVisible(is_bar_plot_vb)
        self.selected_plot.addAction(self.move_to_top)

        self.move_up = QAction("Move up", context_menu)
        self.move_up.triggered.connect(lambda: self.reorder_plots(-1, True))
        self.move_up.setActionGroup(self.selected_plot_group)
        self.move_up.setVisible(is_bar_plot_vb)
        self.selected_plot.addAction(self.move_up)

        self.move_down = QAction("Move down", context_menu)
        self.move_down.triggered.connect(lambda: self.reorder_plots(1, True))
        self.move_down.setActionGroup(self.selected_plot_group)
        self.move_down.setVisible(is_bar_plot_vb)
        self.selected_plot.addAction(self.move_down)

        self.move_to_bottom = QAction("Move to bottom", context_menu)
        self.move_to_bottom.triggered.connect(lambda: self.reorder_plots(-1))
        self.move_to_bottom.setActionGroup(self.selected_plot_group)
        self.move_to_bottom.setVisible(is_bar_plot_vb)
        self.selected_plot.addAction(self.move_to_bottom)

        self.selected_plot.addSection("Reset time option")

        self.reset_selected_axis = QAction("Reset time axis", context_menu)
        self.reset_selected_axis.triggered.connect(lambda: self.reset_times(False))
        self.reset_selected_axis.setActionGroup(self.selected_plot_group)
        self.reset_selected_axis.setVisible(is_line_plot_vb)
        self.selected_plot.addAction(self.reset_selected_axis)

        self.selected_plot.addSection("Misc options")

        self.clear_selected_plot = QAction("Clear file from plot", context_menu)
        self.clear_selected_plot.triggered.connect(self.clear_selected_file)
        self.clear_selected_plot.setActionGroup(self.selected_plot_group)
        self.selected_plot.addAction(self.clear_selected_plot)

        self.selected_plot.addSection("Properties")

        self.view_selected_plot = QAction("View in file browser", context_menu)
        self.view_selected_plot.triggered.connect(self.view_in_browser)
        self.view_selected_plot.setActionGroup(self.selected_plot_group)
        self.selected_plot.addAction(self.view_selected_plot)

        self.view_file_properties = QAction("Properties", context_menu)
        self.view_file_properties.triggered.connect(self.view_properties)
        self.view_file_properties.setActionGroup(self.selected_plot_group)
        self.selected_plot.addAction(self.view_file_properties)

        # Control group for all plots
        self.all_plots = QMenu("All plots", parent=context_menu)
        self.all_plots_group = QActionGroup(self)

        self.zero_all_axes = QAction("Start all time axes at zero", context_menu)
        self.zero_all_axes.triggered.connect(lambda: self.zero_times(True))
        self.zero_all_axes.setActionGroup(self.all_plots_group)
        self.zero_all_axes.setVisible(is_line_plot_vb)
        self.all_plots.addAction(self.zero_all_axes)

        self.ignore_all_before_cursor = QAction("Trim all times before cursor", context_menu)
        self.ignore_all_before_cursor.triggered.connect(lambda: self.trim_plots(True, "Before"))
        self.ignore_all_before_cursor.setActionGroup(self.all_plots_group)
        self.ignore_all_before_cursor.setVisible(is_line_plot_vb)
        self.all_plots.addAction(self.ignore_all_before_cursor)

        self.ignore_all_after_cursor = QAction("Trim all times after cursor", context_menu)
        self.ignore_all_after_cursor.triggered.connect(lambda: self.trim_plots(True, "After"))
        self.ignore_all_after_cursor.setActionGroup(self.all_plots_group)
        self.ignore_all_after_cursor.setVisible(is_line_plot_vb)
        self.all_plots.addAction(self.ignore_all_after_cursor)

        self.all_plots.addSection("Reset time option")

        self.reset_all_axis = QAction("Reset all time axes", context_menu)
        self.reset_all_axis.triggered.connect(lambda: self.reset_times(True))
        self.reset_all_axis.setActionGroup(self.all_plots_group)
        self.reset_all_axis.setVisible(is_line_plot_vb)
        self.all_plots.addAction(self.reset_all_axis)

        self.all_plots.addSection("Misc options")

        self.clear_all_plots = QAction("Clear all files", context_menu)
        self.clear_all_plots.triggered.connect(self.clear_files)
        self.clear_all_plots.setActionGroup(self.all_plots_group)
        self.all_plots.addAction(self.clear_all_plots)

        # Toggle crosshair cursor
        self.toggle_cursor = QAction("Toggle crosshair cursor", context_menu)
        self.toggle_cursor.setVisible(is_line_plot_vb)
        self.toggle_cursor.setCheckable(True)
        self.toggle_cursor.triggered.connect(self.toggle_crosshair_cursor)

        # Left mouse mode group
        self.lmb_mode: QMenu = QMenu("Left click mode", parent=context_menu)
        self.lmb_mode_group = QActionGroup(self)

        self.lmb_pan = QAction("Pan", self.lmb_mode)
        self.lmb_pan.triggered.connect(self.lmb_mode_pan)
        self.lmb_pan.setCheckable(True)
        self.lmb_pan.setChecked(True)
        self.lmb_pan.setActionGroup(self.lmb_mode_group)
        self.lmb_mode.addAction(self.lmb_pan)

        self.lmb_zoom = QAction("Zoom", self.lmb_mode)
        self.lmb_zoom.triggered.connect(self.lmb_mode_zoom)
        self.lmb_zoom.setCheckable(True)
        self.lmb_zoom.setActionGroup(self.lmb_mode_group)
        self.lmb_mode.addAction(self.lmb_zoom)

        # Toggle crosshair cursor
        self.r_squared = QAction("Show r-squared in legend", context_menu)
        self.r_squared.setVisible(is_scatter_plot_vb)
        self.r_squared.setCheckable(True)
        self.r_squared.triggered.connect(self.show_r_squared)

        self.fit_to_view = QAction("Fit to view", context_menu)
        self.fit_to_view.triggered.connect(self.autoRange)

        self.export_plot = QAction("Save as image", context_menu)
        self.export_plot.triggered.connect(self.export_image)

        # Add menu items in the order they'll appear
        context_menu.addMenu(self.selected_plot)
        context_menu.addMenu(self.all_plots)
        context_menu.addSection("Mouse controls")
        context_menu.addAction(self.toggle_cursor)
        context_menu.addMenu(self.lmb_mode)

        if is_scatter_plot_vb:
            context_menu.addSection("Scatter plot controls")
            context_menu.addAction(self.r_squared)

        context_menu.addSection("Misc controls")
        context_menu.addAction(self.fit_to_view)
        context_menu.addAction(self.export_plot)

        return context_menu

    def getMenu(self) -> QMenu:
        """Create the menu. Enable plot-based actions if a plot is selected."""
        plot_selected = PlotObject.get_selected() is not None
        self.selected_plot.setEnabled(plot_selected)
        self.context_menu.setStyleSheet(current_stylesheet())
        return self.context_menu

    @pyqtSlot(int)
    def set_lmb_mode(self, mode: int) -> None:
        """Match class state for LMB mode and update the context menu accordingly.

        Args:
            * mode (int): Rectangular zoom (1) or panning (3). Default is 3.
        """
        try:
            self.setMouseMode(mode)
            lmb_mode = self.lmb_zoom if mode == 1 else self.lmb_pan
            lmb_mode.setChecked(True)
        except AttributeError:
            pass  # Suppress class-level error messages
        except Exception as e:
            raise e from e

    @staticmethod
    def lmb_mode_zoom() -> None:
        """Set mouse mode to rectangular selection zoom."""
        ContextMenuViewBox.lmb_mode_changed.signal.emit(1)

    @staticmethod
    def lmb_mode_pan() -> None:
        """Set mouse mode to pan."""
        ContextMenuViewBox.lmb_mode_changed.signal.emit(3)

    def toggle_crosshair_cursor(self) -> None:
        """Set cursor mode for all plots."""
        self.lmb_mode_pan()
        ContextSignal.emit(MenuOption.ToggleCursor.value)

    @staticmethod
    def set_plot_color() -> None:
        """Raise a color picker dialog window for changing the selected plot's pen color."""
        selected = PlotObject.get_selected()
        new_color = color_picker(selected.pen)
        if new_color is not None:
            selected.pen = new_color
            PlotObject.update_selected_pen()

    def emit_modify_file_signal(self, all_files: bool) -> None:
        """Generic signal to indicate that plots should be refreshed after an event."""
        ContextSignal.emit(
            MenuOption.ModifyAllFiles.value if all_files else MenuOption.ModifySelectedFile.value
        )

    def reset_times(self, all_files: bool) -> None:
        """Revert the time series back to normal for one file or all plotted files.

        Args:
            * all_files (bool): Determines whether to update the selected file or all files.
        """
        if session("CurrentTabIndex") != Tab.Line.value:
            return

        PlotObject.reset_file_time(all_files)
        self.emit_modify_file_signal(all_files)

    def zero_times(self, all_files: bool) -> None:
        """Zero the beginning of the displayed time series for one file or all plotted files.

        Args:
            * all_files (bool): Determines whether to update the selected file or all files.
        """
        if session("CurrentTabIndex") != Tab.Line.value:
            return

        PlotObject.zero_file_time(all_files)
        self.emit_modify_file_signal(all_files)

    def trim_plots(self, all_files: bool, relation: str) -> None:
        """Alter the time series for one file or all plotted files.

        Args:
            * all_files (bool): Determines whether to update the selected file or all files.
        """
        if session("CurrentTabIndex") != Tab.Line.value:
            return

        PlotObject.trim_file_time(all_files, relation, self.cursor_position)
        self.emit_modify_file_signal(all_files)

    def reorder_plots(self, index: int = 0, relative: bool = False) -> None:
        """Reorder the plotted files according to user input."""
        SquareLegendItem.reorder_legend_item(index, relative)
        ContextSignal.emit(MenuOption.ReorderLegend.value)

    def show_r_squared(self) -> None:
        """Toggle the display of a plot's r-squared value in its legend entry."""
        set_session_value("ShowRSquaredValue", self.r_squared.isChecked())
        ContextSignal.emit(MenuOption.RefreshPlots.value)

    @staticmethod
    def view_in_browser() -> None:
        """Load this file's data into the file browser and change the viewed tab index."""
        ContextSignal.emit(MenuOption.ViewInBrowser.value)

    @staticmethod
    def view_properties() -> None:
        """Open a dialog window for viewing and modifying a file's properties."""
        ContextSignal.emit(MenuOption.ViewProperties.value)

    @staticmethod
    def clear_selected_file() -> None:
        """Clear the selected file from all plots."""
        ContextSignal.emit(MenuOption.ClearFile.value)

    @staticmethod
    def clear_files() -> None:
        """Clear all files from all plots."""
        ContextSignal.emit(MenuOption.ClearAllFiles.value)

    def export_image(self) -> None:
        """Pass the pyqtgraph scene to core.exporter to be written to an image."""
        # Hide the cursor (also disabling downsampling) while saving image
        cursor_visible: bool = self.toggle_cursor.isChecked()
        if cursor_visible:
            self.toggle_crosshair_cursor()

        pq_exporter = ImageExporter(self.scene())
        write_image(pq_exporter)

        if cursor_visible:
            self.toggle_crosshair_cursor()
