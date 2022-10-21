"""This module contains a subclass for PyQt6's QStyledItemDelegate."""


from contextlib import suppress

from core.configuration import session, setting
from core.utilities import mutable_table_headers, preserve_marks, stat_table_headers

from PyQt6.QtGui import QBrush, QColor, QPalette
from PyQt6.QtWidgets import QStyledItemDelegate


_DIMINISHED_PHRASES: tuple = ("UNKNOWN", "NONE", "N/A")


class SignalingDelegate(QStyledItemDelegate):
    """Subclass of the styled item delegate that will emit Qt signal after editing a cell.

    This delegate will only allow specific columns to be edited, and the emitted signal is used by
    MainWindow to update the PlotObject associated with the modified cell to allow the user to
    manually provide or correct file metadata (application, resolution, etc.)
    """

    _table_headers: list[str] = list(stat_table_headers().keys())
    _mutable_headers: list[str] = mutable_table_headers()
    _path_index: int = _table_headers.index("File Location")
    _stutter_columns: list[int] = [
        list(_table_headers).index("Proportion\nof Stutter"),
        list(_table_headers).index("Average\nStutter"),
        list(_table_headers).index("Maximum\nStutter"),
    ]

    relative_stats: bool = False

    @classmethod
    def update_table_headers(cls) -> None:
        """Update class variables with current table headers."""
        cls._table_headers = list(stat_table_headers().keys())

    def createEditor(self, parent, option, index) -> None:
        """Only allow fields of mutable properties to be edited."""
        if SignalingDelegate._table_headers[index.column()] in SignalingDelegate._mutable_headers:
            return super(SignalingDelegate, self).createEditor(parent, option, index)

    def initStyleOption(self, option, index) -> None:
        """Impart conditional formatting for cells with important values."""
        super().initStyleOption(option, index)

        cfg = setting
        data = index.data()
        idx: int = index.column()
        dark_mode: bool = session("DarkMode")
        diminishing_fallback: bool = cfg("General", "DiminishFallbacks") == "True"

        # Diminish fallback values for lower visual density with populated tables
        if not isinstance(data, str):
            return
        elif diminishing_fallback and data.upper() in _DIMINISHED_PHRASES:
            option.palette.setBrush(
                QPalette.ColorRole.Text, QBrush(QColor("#555555" if dark_mode else "#aaaaaa"))
            )
        # Conditionally format rows for files affected by oscillations or stutter events
        elif (
            idx in SignalingDelegate._stutter_columns
            and not SignalingDelegate.relative_stats
            and data != "N/A"
        ):
            oscillation: bool = False
            prop_stutter: bool = False
            avg_stutter: bool = False
            max_stutter: bool = False

            oscillation = idx in SignalingDelegate._stutter_columns[1:] and data == "OSC"
            if not oscillation:
                with suppress(Exception):
                    data = float(data[:-1].replace(",", ""))
                    prop_stutter = idx == SignalingDelegate._stutter_columns[0] and data >= float(
                        cfg("StutterHeuristic", "StutterWarnPct")
                    )
                    avg_stutter = idx == SignalingDelegate._stutter_columns[1] and data >= float(
                        cfg("StutterHeuristic", "StutterWarnAvg")
                    )
                    max_stutter = idx == SignalingDelegate._stutter_columns[2] and data >= float(
                        cfg("StutterHeuristic", "StutterWarnMax")
                    )
            if any((oscillation, prop_stutter, avg_stutter, max_stutter)):
                option.backgroundBrush = QBrush(QColor("#382626" if dark_mode else "#fff0f0"))
                option.palette.setBrush(QPalette.ColorRole.Text, QBrush(QColor("#af2121")))

    def setModelData(self, editor, model, index) -> None:
        """Only commit changed values to the model and protect integrity indicators (asterisks)."""
        previous_value: str = index.data()
        new_value: str = preserve_marks(previous_value, editor.text())

        if previous_value != new_value:
            editor.setText(new_value)
            super().setModelData(editor, model, index)
