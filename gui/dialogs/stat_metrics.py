"""This module builds a dialog window for modifying capture file properties."""

from base64 import urlsafe_b64decode
from json import loads

from core.configuration import set_value, setting
from core.logger import get_logger, log_exception
from core.utilities import stat_table_headers
from gui.layouts.stat_metrics import Ui_Dialog
from gui.styles import current_stylesheet
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog

logger = get_logger(__name__)


class StatMetricsDialog(QDialog, Ui_Dialog):
    """Builds and updates a PyQt6 GUI."""

    def __init__(self, parent) -> None:
        super().__init__(parent=parent)
        self.setupUi(self)

        # Hide 'What's This?' button and disallow resizing
        flags = self.windowFlags()
        self.setWindowFlags(
            flags | Qt.WindowType.MSWindowsFixedSizeDialogHint | Qt.WindowType.CoverWindow
        )

        self.defaults: dict = loads(
            urlsafe_b64decode(setting("Statistics", "Visibility", default=True))
        )
        self.headers: list = list(stat_table_headers().keys())

        # Any modifications to the column headers MUST be copied in the MainWindow instance
        # variable in core.utilities as well as the four categorical methods in PlotObject.
        self.widgets: list = [
            # Capture metadata
            self.check_metric_capture_type,
            self.check_metric_capture_integrity,
            self.check_metric_application,
            self.check_metric_resolution,
            self.check_metric_runtime,
            self.check_metric_gpu,
            self.check_metric_comments,
            # Display metrics
            self.check_metric_duration,
            self.check_metric_frames,
            self.check_metric_synced_frames,
            # Performance
            self.check_metric_min_fps,
            self.check_metric_average_fps,
            self.check_metric_median_fps,
            self.check_metric_max_fps,
            # Performance (percentiles)
            self.check_metric_low_0_1,
            self.check_metric_pct_0_1,
            self.check_metric_low_1,
            self.check_metric_pct_1,
            self.check_metric_pct_5,
            self.check_metric_pct_10,
            # Relative performance metrics
            self.check_metric_low_0_1_over_avg,
            self.check_metric_pct_0_1_over_avg,
            self.check_metric_low_1_over_avg,
            self.check_metric_pct_1_over_avg,
            self.check_metric_pct_5_over_avg,
            self.check_metric_pct_10_over_avg,
            # Stutter metrics
            self.check_metric_stutter_number,
            self.check_metric_stutter_proportional,
            self.check_metric_stutter_average,
            self.check_metric_stutter_max,
            # GPU metrics
            self.check_metric_present_latency,
            self.check_metric_perf_per_watt,
            self.check_metric_gpu_board_power,
            self.check_metric_gpu_chip_power,
            self.check_metric_gpu_frequency,
            self.check_metric_gpu_temperature,
            self.check_metric_gpu_utilization,
            self.check_metric_gpu_voltage,
            # CPU metrics
            self.check_metric_cpu_power,
            self.check_metric_cpu_frequency,
            self.check_metric_cpu_temperature,
            self.check_metric_cpu_utilization,
            # Battery metrics
            self.check_metric_battery_charge,
            self.check_metric_battery_life,
            # Capture metadata (continued)
            self.check_metric_file_name,
            self.check_metric_file_path,
        ]

        self.update_selection()

    def exec(self) -> int:
        """Execute the dialog and return 0 if user canceled or 1 if they saved changes."""
        self.update_selection()
        self.setStyleSheet(current_stylesheet())
        return super().exec()

    def reset_to_defaults(self) -> None:
        """Set all statistics metrics to default."""
        selections = loads(urlsafe_b64decode(setting("Statistics", "Visibility", default=True)))
        for widget, visibility in zip(self.widgets, selections.values()):
            widget.setChecked(bool(visibility))

        self.combo_percentile_method.setCurrentText(
            setting("Statistics", "PercentileMethod", default=True)
        )

    def current_selection(self) -> dict:
        """Return the selection as a dictionary of names and states."""
        set_value("Statistics", "PercentileMethod", self.combo_percentile_method.currentText())
        return dict(zip(self.headers, [widget.isChecked() for widget in self.widgets]))

    def update_selection(self) -> None:
        """Match widget states to the user config."""
        try:
            decoded_selections = urlsafe_b64decode(str.encode(setting("Statistics", "Visibility")))
            selections = loads(decoded_selections)

            if self.defaults.keys() != selections.keys():
                logger.debug("Using default settings for statistics metrics")
                selections = self.defaults
        except Exception as e:
            log_exception(logger, e, "Failed to decode stat visibility data")
            selections = self.defaults
        finally:
            self.combo_percentile_method.setCurrentText(setting("Statistics", "PercentileMethod"))
            for widget, visibility in zip(self.widgets, selections.values()):
                widget.setChecked(bool(visibility))
