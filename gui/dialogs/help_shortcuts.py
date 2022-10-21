"""This module shows a simple dialog window with keyboard shortcuts."""

from gui.layouts.help_shortcuts import Ui_Dialog
from gui.styles import current_stylesheet
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog


class HelpShortcutsDialog(QDialog, Ui_Dialog):
    def __init__(self) -> None:
        super().__init__()
        self.setupUi(self)

        # Hide 'What's This?' button and disallow resizing
        flags = self.windowFlags()
        self.setWindowFlags(
            flags | Qt.WindowType.MSWindowsFixedSizeDialogHint | Qt.WindowType.CoverWindow
        )

        self.setStyleSheet(current_stylesheet())
