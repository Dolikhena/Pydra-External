"""This module builds a dialog window for modifying capture file properties."""

from core.configuration import session
from core.logger import get_logger
from gui.layouts.manage_axes import Ui_Dialog
from gui.styles import current_stylesheet
from PyQt6.QtWidgets import QDialog

logger = get_logger(__name__)


class ManageLinePlotAxes(QDialog, Ui_Dialog):
    """Builds and updates a PyQt6 GUI.

    This is a placeholder module until pyqtgraph has accepted the MultiAxisPlotWidget
    pull request #1359: https://github.com/pyqtgraph/pyqtgraph/pull/1359
    """

    def __init__(self, model) -> None:
        super(ManageLinePlotAxes, self).__init__()
        self.setupUi(self)
        self.setStyleSheet(current_stylesheet())

        self.combo_data_source_1.setModel(model)
        self.combo_data_source_2.setModel(model)
        self.combo_data_source_3.setModel(model)
        self.combo_data_source_4.setModel(model)

        self.combo_data_source_1.setCurrentText(session("PrimaryDataSource"))
        self.combo_data_source_2.setCurrentText(session("SecondaryDataSource"))
