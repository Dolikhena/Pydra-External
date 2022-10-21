"""This module contains a subclass for PyQt6's QListWidget and QListWidgetItem."""

from typing import Optional

from core.configuration import session
from core.logger import get_logger
from core.utilities import color_picker
from formats.integrity import Integrity
from gui.contextsignals import ContextSignal, MenuOption
from gui.plotobject import PlotObject
from gui.pyqtgraph.legenditem import SquareLegendItem
from gui.styles import current_stylesheet

from PyQt6.QtCore import QPoint, Qt, pyqtSlot
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QMenu

logger = get_logger(__name__)


class FlexibleListItem(QListWidgetItem):
    """Subclass of PyQt6's QListWidgetItem, modified to support dynamic display text."""

    def __init__(self, file_path: str) -> None:
        super().__init__(file_path)
        self._display_text: str = "Loading..."
        self.path: str = file_path
        self.plot_obj = None

    def properties(self) -> dict:
        """Return the properties dict of the file."""
        file = self.plot_obj.file
        return {
            "Capture Type": file.app_name,
            "Application": file.properties["Application"],
            "Resolution": file.properties["Resolution"],
            "Runtime": file.properties["Runtime"],
            "GPU": file.properties["GPU"],
            "Comments": file.properties["Comments"],
            "File Name": file.name,
            "File Path": self.path,
        }

    def update_label(self) -> None:
        """Change the displayed text to match the selected format."""
        if self.plot_obj is None:
            return

        text_format: str = session("FileDisplayFormat")
        display_text = self.properties()[text_format]

        # Improve readibility for undefined properties
        if display_text == "Unknown":
            display_text += f" {text_format}"

        self._display_text = display_text

    def data(self, role: int) -> str:
        """Return the text in the format selected by the user."""
        return self._display_text if role == 0 else super().data(role)


class ContextMenuListWidget(QListWidget):
    """Subclass of PyQt6's QListWidget, modified to support custom context menus."""

    _HIDE_INVALID_FILES: bool = False

    @classmethod
    def hide_invalid_files(cls, hide: bool) -> None:
        cls._HIDE_INVALID_FILES = hide

    def __init__(self, parent=None) -> None:
        ContextMenuListWidget._widget = self
        super(ContextMenuListWidget, self).__init__(parent)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.raise_context_menu)

        self._label_filter: dict = {}
        self._selection: list[str] = []
        self.context_menu = self.create_menu()
        self.target_file: Optional[str] = None

    def item_by_path(self, file_path: str) -> Optional[FlexibleListItem]:
        """Return the list item matching the selected file path."""
        return next((item for item in self.items() if item.path == file_path), None)

    def items(self) -> list:
        """Single dispatch method for returning all current items."""
        return [self.item(x) for x in range(self.count())]  # if not self.item(x).isHidden()

    def update_icon(self, file_path: str, integrity: Integrity, icon: QIcon) -> None:
        """Update the integrity icon next to each loaded file in `list_loaded_files`.

        Called after a file has been made as a PlotObject.
        """
        self.save_selection_state()

        if item := self.item_by_path(file_path):
            plot_obj = PlotObject.get_by_path(file_path)

            if plot_obj is not None:
                if item.plot_obj is None:
                    item.plot_obj = plot_obj
                item.update_label()
                item.setToolTip(plot_obj.tooltip())
            else:
                item.setToolTip(integrity.description())

            item.setIcon(icon)

            # Enable normal interaction flags for valid integrities
            if integrity.valid():
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)

            self.filter_label(item)

        self.restore_selection_state()

    def update_all_labels(self) -> None:
        """Update all current items to the currently selected format."""
        self.save_selection_state()

        for item in self.items():
            item.update_label()

        self.restore_selection_state()
        self.doItemsLayout()

    def filter_all_labels(self) -> None:
        """Filter all items by the current filters."""
        for item in self.items():
            self.filter_label(item)

    def filter_label(self, item) -> None:
        """Apply filter rules against a label item, deselecting it if hidden."""
        if item.plot_obj is None:
            return

        item.setHidden(False)
        file_properties = item.properties()

        for include, field_and_terms in self._label_filter.items():
            if field_and_terms == {}:
                continue

            for field, term in field_and_terms.items():
                # Hide invalid files
                if not include and field == "Invalid":
                    if item.plot_obj is None or not item.plot_obj.file.integrity.valid():
                        item.setHidden(True)
                else:
                    self.hide_matches(item, file_properties[field].lower(), include, term)

                if item.isHidden():
                    return item.setSelected(False)

    def hide_matches(self, item, file_property, include, term) -> None:
        """Hide a list item if its file property matches a filter criterion."""
        if "," in term:
            terms = term.split(",")
            for split_term in terms:
                item.setHidden(include)
                if split_term and split_term in file_property:
                    return item.setHidden(not include)
        elif term in file_property:
            return item.setHidden(not include)
        return item.setHidden(include)

    def update_label_filter(self, filters: dict) -> None:
        """Update the label filter definition and apply it to current items."""
        self._label_filter = filters
        self.filter_all_labels()

    def save_selection_state(self) -> None:
        """Collect the file paths of selected items."""
        self._selection = self.get_selected_item_paths()

    def restore_selection_state(self) -> None:
        """Store the previous item selection according to file path."""
        for item in self._selection:
            self.item_by_path(item).setSelected(True)

    @pyqtSlot(object, object)
    def emphasize_selected_file(self) -> None:
        """Change the font weight of the selected file in the loaded file list."""
        selected = session("SelectedFilePath")
        for item in self.items():
            selected_file: bool = item.path == selected
            font = item.font()
            font.setBold(selected_file)
            item.setFont(font)

            if selected_file:
                self.scrollToItem(item)

        SquareLegendItem.update_all()

    @pyqtSlot(QPoint)
    def raise_context_menu(self, pos: QPoint) -> None:
        """Raise the context menu at the cursor when user right-clicks in a pyqtgraph region."""
        # QListWidget requires relative coordinates for selecting an item
        widget_coords = self.viewport().mapFromParent(pos)
        item_beneath_cursor: FlexibleListItem = self.itemAt(widget_coords.x(), widget_coords.y())

        # Don't raise context menu in empty space
        if item_beneath_cursor is None:
            return

        self.target_file = item_beneath_cursor

        # Only raise menu if there's an item beneath the cursor position
        if self.target_file is not None:
            menu = self.get_menu()
            menu.exec(self.sender().mapToGlobal(pos))

    def create_menu(self) -> QMenu:
        """Define the layout and actions for each ViewBox's context menu."""
        context_menu: QMenu = QMenu()

        # Select this file's plot
        self.select_target_file: QAction = QAction("Select plot", context_menu)
        self.select_target_file.triggered.connect(self.select_file)

        # Change this file's plot colors
        self.raise_color_picker = QAction("Change plot color", context_menu)
        self.raise_color_picker.triggered.connect(self.set_plot_color)

        # Reset this plot's time offset
        self.reset_time_offset = QAction("Reset time offset", context_menu)
        self.reset_time_offset.triggered.connect(self.reset_file_times)

        # View file in browser
        self.view_in_browser = QAction("View in file browser", context_menu)
        self.view_in_browser.triggered.connect(self.view_file_in_browser)

        # View/modify file properties
        self.view_file_properties = QAction("Properties", context_menu)
        self.view_file_properties.triggered.connect(self.view_properties)

        # Add menu items in the order they'll appear
        context_menu.addAction(self.select_target_file)
        context_menu.addAction(self.raise_color_picker)
        context_menu.addSeparator()
        context_menu.addAction(self.reset_time_offset)
        context_menu.addSeparator()
        context_menu.addAction(self.view_in_browser)
        context_menu.addAction(self.view_file_properties)

        return context_menu

    def get_menu(self) -> QMenu:
        """Return the context menu with items selectively enabled."""
        # Get file name and PlotObject instance of the file beneath cursor
        plot_obj: PlotObject = self.target_file.plot_obj
        valid_file = plot_obj.file.integrity.valid()
        is_plotted = valid_file and plot_obj.plotted

        # Stateful option toggling
        self.select_target_file.setVisible(valid_file)
        self.reset_time_offset.setVisible(valid_file)
        self.raise_color_picker.setVisible(valid_file)
        self.view_file_properties.setVisible(valid_file)

        if valid_file:
            self.select_target_file.setEnabled(is_plotted)

        self.context_menu.setStyleSheet(current_stylesheet())
        return self.context_menu

    def get_selected_items(self) -> list:
        """Return the associated PlotObjects of currently selected items."""
        return [item.plot_obj for item in self.selectedItems()]

    def get_selected_item_paths(self) -> list:
        """Return the file paths of currently selected items."""
        return sorted(item.path for item in self.selectedItems())

    def select_file(self) -> None:
        """Highlight a file's plots, identical to clicking a plot from the pyqtgraph widgets."""
        PlotObject.select_by_path(self.target_file.path)
        ContextSignal.emit(MenuOption.SelectFile.value)

    def set_plot_color(self) -> None:
        """Raise a color picker dialog window for changing the selected file's pen color."""
        plot_obj: PlotObject = self.target_file.plot_obj

        new_color = color_picker(plot_obj.pen)
        if new_color is not None:
            plot_obj.pen = new_color
            PlotObject.update_object_pen(plot_obj)

    def reset_file_times(self) -> None:
        """Remove offsets and trimming from all plotted files."""
        self.target_file.plot_obj.file.reset_time_axis()
        ContextSignal.emit(MenuOption.ModifySelectedFile.value)

    def view_file_in_browser(self) -> None:
        """Load this file into the file browser and switch tab view."""
        ContextSignal.emit(MenuOption.ViewInBrowser.value)

    def view_properties(self) -> None:
        """Raise a dialog window for viewing/editing a file's properties."""
        ContextSignal.emit(MenuOption.ViewProperties.value)
