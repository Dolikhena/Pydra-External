"""This module contains a subclass for PyQt6's QTableView."""

from core.stopwatch import stopwatch
from gui.PyQt6.delegate import SignalingDelegate, preserve_marks

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import QTableView


class CustomSortItem(QStandardItem):
    """Subclass of the standard item object with better support for mixed display formats."""

    @stopwatch(silent=True)
    def __lt__(self, other):
        this = self.text()
        that = other.text()

        try:
            this = float(this.replace("%", "").replace(",", ""))
            that = float(that.replace("%", "").replace(",", ""))
        except Exception:
            return str(this) < str(that)  # For incompatible comparisons (float vs str)
        return this < that


class SharedEditTableView(QTableView):
    """Subclass of the table view widget, modified to propagate edits over a selected column."""

    cell_edited = pyqtSignal(str, str, str)

    def __init__(self, parent) -> None:
        super().__init__(parent=parent)
        self.delegate = SignalingDelegate()
        self.set_header_labels()

    def set_header_labels(self) -> None:
        """Set the column headers. Used on init and when changing the time scale."""
        self.table_stats_header_labels = SignalingDelegate._table_headers
        self.table_stats_header_count = len(self.table_stats_header_labels)

    def update_header_visibility(self, visibility: dict) -> None:
        """Adjust the visibility of each column based on the user selection."""
        for index, is_visible in enumerate(visibility.values()):
            self.setColumnHidden(index, not is_visible)
        self.resizeColumnsToContents()

    def reset_view(self) -> None:
        """Reset the table to default state."""
        stats_model = QStandardItemModel(0, self.table_stats_header_count)
        stats_model.setHorizontalHeaderLabels(self.table_stats_header_labels)
        self.setModel(stats_model)
        self.resizeColumnsToContents()

    def commitData(self, editor) -> None:
        """Change the value of a selected cell.

        If multiple cells are selected, all cells within the same column will be updated with the
        new value, and these changes will be propagated to their respective PlotObjects.
        """
        model = self.currentIndex().model()
        current_col: int = self.currentIndex().column()
        edited_property: str = SignalingDelegate._table_headers[current_col]
        selection = self.selectionModel().selection()

        for cell in selection:
            rows = range(cell.top(), cell.bottom() + 1)
            for row in rows:
                index = model.index(row, current_col)
                previous_value = model.data(index)
                new_value = preserve_marks(model.data(index), editor.text())

                if previous_value != new_value:
                    self.delegate.setModelData(editor, model, index)
                    path = index.siblingAtColumn(self.delegate._path_index).data()
                    self.cell_edited.emit(path, edited_property, model.data(index))

        super(SharedEditTableView, self).commitData(editor)
