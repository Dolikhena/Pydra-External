"""This module builds a dialog window for modifying capture file properties."""

from pathlib import Path
from subprocess import Popen

from core.logger import get_logger, log_exception
from core.utilities import color_picker
from gui.layouts.file_properties import Ui_Dialog
from gui.metadata import remove_record
from gui.plotobject import PlotObject
from gui.styles import current_stylesheet
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog

logger = get_logger(__name__)


class FilePropertyDialog(QDialog, Ui_Dialog):
    def __init__(self, plot_obj: PlotObject) -> None:
        super().__init__()
        self.setupUi(self)
        self.changed_values: bool = False
        self.plot_obj: PlotObject = plot_obj

        # Hide 'What's This?' button and disallow resizing
        flags = self.windowFlags()
        self.setWindowFlags(
            flags | Qt.WindowType.MSWindowsFixedSizeDialogHint | Qt.WindowType.CoverWindow
        )

        self.setStyleSheet(f"{current_stylesheet()} QLineEdit:read-only {{color: #888}}")
        self.caution_label_pen_width.setStyleSheet("QLabel {min-height: 60px; max-height: 200px;}")

        # Show warning label for line widths above 1 pixel
        self.caution_label_pen_width.setVisible(False)
        self.spin_pen_width.valueChanged.connect(
            lambda: self.caution_label_pen_width.setVisible(self.spin_pen_width.value() > 1)
        )

        # Use initial hash of file properties to detect changes
        self.update_widget_text()
        self.update_pen_parameters()
        self.initial_values: int = self.hash_widget_values()

    def hash_widget_values(self) -> int:
        """Return the hash of current file properties."""
        return hash(
            (
                (widget.text() for widget in self.widget_data.keys()),
                self.check_use_custom_legend.isChecked(),
                self.plot_obj.pen,
                self.plot_obj.width,
            )
        )

    def accept(self) -> None:
        """Update variable if changes have been made after clicking OK."""
        self.changed_values = self.initial_values != self.hash_widget_values()
        return super().accept()

    def update_widget_text(self) -> None:
        """Set the values of property widgets to match the PlotObject."""
        try:
            file_properties = self.plot_obj.file.properties

            self.widget_data: dict = {
                self.line_property_capture_type: self.plot_obj.file.app_name,
                self.line_property_application: file_properties["Application"],
                self.line_property_resolution: file_properties["Resolution"],
                self.line_property_runtime: file_properties["Runtime"],
                self.line_property_gpu: file_properties["GPU"],
                self.line_property_comments: file_properties["Comments"],
                self.line_property_file_name: Path(self.plot_obj.file.path).name,
                self.line_property_file_path: self.plot_obj.file.path,
                self.line_custom_legend: file_properties["Legend"][1],
            }

            for widget, text in self.widget_data.items():
                widget.setText(text)
            self.check_use_custom_legend.setChecked(file_properties["Legend"][0])

        except KeyError as e:
            log_exception(logger, e, "Missing PlotObject property key")
        except Exception as e:
            log_exception(logger, e)

    def update_pen_parameters(self) -> None:
        """Style a push button as the pen color."""
        pen: tuple = self.plot_obj.pen
        pen_rgb: str = f"rgb({pen[0]}, {pen[1]}, {pen[2]})"
        self.btn_pen_color.setStyleSheet(
            f"""
            QPushButton#btn_pen_color {{
                background-color: {pen_rgb};
                border-color: {pen_rgb};
                height: 20px;
                width: 50px;
                padding: 0;
                margin: 0;
            }}
            QPushButton#btn_pen_color:hover {{
                border: 2px solid #76b900;
            }}
            """
        )

        self.spin_pen_width.setValue(self.plot_obj._width)

    def change_pen_color(self) -> None:
        """Raise a color picker dialog window for changing the file's pen color."""
        new_color = color_picker(self.plot_obj.pen)

        if new_color is not None:
            self.plot_obj.pen = new_color
            PlotObject.update_object_pen(self.plot_obj)
            self.update_pen_parameters()

    def open_file_location(self) -> None:
        """Create a native file explorer dialog selecting the current file."""
        file_path: Path = Path(self.line_property_file_path.text()).resolve()
        if file_path.exists:
            Popen(f"explorer /select,{file_path}", shell=False)

    def reset_file_properties(self) -> None:
        """Revert modifications to a capture file's properties and remove its metadata record."""
        remove_record(self.plot_obj.file.hash, "Properties")
        self.plot_obj.file.uses_saved_properties = False

        self.plot_obj.file.define_properties()
        self.plot_obj.file.properties["Comments"] = "None"

        self.update_widget_text()
        self.accept()
