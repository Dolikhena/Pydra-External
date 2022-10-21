"""This module contains a subclass for PyQt6's QAbstractTableModel."""

from typing import Optional

from core.logger import get_logger, log_exception
from pandas import DataFrame

from PyQt6.QtCore import QAbstractTableModel, Qt

logger = get_logger(__name__)


class DataFrameTableModel(QAbstractTableModel):
    """Subclass of the abstract table model, modified to work with DataFrames."""

    def __init__(self, data=None, parent=None) -> None:
        super().__init__(parent=parent)
        self._data: DataFrame = (
            DataFrame()
            if data is None
            else data
            if isinstance(data, DataFrame)
            else DataFrame(data)
        )
        self._columns = self._data.columns
        self.r, self.c = self._data.shape

    def rowCount(self, parent=None) -> int:
        """Return the number of rows."""
        return self.r

    def columnCount(self, parent=None) -> int:
        """Return the number of columns."""
        return self.c

    def headerData(
        self, column: int, orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Optional[list]:
        """Return the header data for a given row/column.

        Args:
            * col (int): Index of the column.
            * orientation (int): Descending (0) or ascending (1) order.
            * role (int): Used by the view to indicate to the model what type of data is needed.
        """
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                try:
                    return self._columns[column]
                except Exception:
                    return None
            elif orientation == Qt.Orientation.Vertical:
                try:
                    return int(self._data.index[column]) + 1
                except Exception:
                    return None
        return None

    def data(self, index, role: int = Qt.ItemDataRole.DisplayRole) -> Optional[str]:
        """Return the data for the current index.

        This is called through many events: updating a model, hovering over a widget, selecting
        an item from a list, etc.
        """
        if index.isValid() and role == Qt.ItemDataRole.DisplayRole:
            return str(self._data.iloc[index.row(), index.column()])
        return None

    def sort(self, column: int, direction: int) -> None:
        """Emit signals before and after sorting this subclass to improve performance.

        Args:
            * column (int): Column index being sorted.
            * direction (int): Descending (0) or ascending (1) order.
        """
        self.layoutAboutToBeChanged.emit()

        try:
            self._data = self._data.sort_values(self._columns[column], ascending=direction)
        except ValueError:
            pass  # Suppress errors when failing to sort non-numeric columns
        except Exception as e:
            log_exception(logger, e, f"Error sorting {self._columns[column]}")

        self.layoutChanged.emit()
