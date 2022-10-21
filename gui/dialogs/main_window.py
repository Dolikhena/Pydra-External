"""This module is responsible for constructing and updating the Pydra GUI."""

from base64 import urlsafe_b64encode
from json import dumps
from logging import getLogger
from os import getenv, getpid, walk
from pathlib import Path
from subprocess import run
from time import perf_counter_ns
from typing import Any, Callable, Generator
from webbrowser import open as open_browser

from core.configuration import (
    app_root,
    default_value,
    running_from_exe,
    session,
    set_defaults,
    set_session_value,
    set_value,
    setting,
    setting_bool,
)
from core.exporter import output_location, write_file_view, write_stats_file
from core.logger import GUILogger, get_logger, log_chapter, log_exception, log_table, logging_path
from core.stopwatch import Welford, stopwatch, time_from_ns
from core.update import current_version_str, update_available
from core.utilities import (
    Tab,
    default_data_sources,
    preserve_marks,
    size_from_bytes,
    stat_table_headers,
    time_scale,
    time_str_long,
)
from formats.integrity import Integrity
from gui.contextsignals import ContextSignal, MenuOption
from gui.dialogs.file_properties import FilePropertyDialog
from gui.dialogs.help_shortcuts import HelpShortcutsDialog
from gui.dialogs.stat_metrics import StatMetricsDialog
from gui.layouts.main_window import Ui_MainWindow

# from gui.layouts.manageaxes import ManageLinePlotAxes
from gui.metadata import remove_all_records, remove_section, update_metadata_file, update_record
from gui.plotobject import PlotObject
from gui.PyQt6.listwidget import FlexibleListItem
from gui.PyQt6.statusbar import StatusBarWithQueue
from gui.PyQt6.tablemodel import DataFrameTableModel
from gui.PyQt6.tableview import CustomSortItem, SharedEditTableView, SignalingDelegate
from gui.pyqtgraph.plotdataitem import ClickableErrorBarItem, UnclickableBarGraphItem
from gui.pyqtgraph.plotwidget import ContextMenuPlotWidget
from gui.pyqtgraph.viewbox import SquareLegendItem
from gui.styles import current_stylesheet, icon_path
from gui.worker import Worker
from numpy import min, repeat
from pandas import DataFrame
from psutil import Process
from PyQt6.QtCore import Qt, QThreadPool, QTimer, pyqtSlot
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QFont, QFontDatabase, QShortcut
from PyQt6.QtWidgets import QApplication, QDialog, QFileDialog, QMainWindow, QMessageBox
from pyqtgraph import PlotDataItem, SignalProxy, TextItem, setConfigOptions

if running_from_exe():
    # Change splash messages and hide the window after unpacking
    import pyi_splash


logger = get_logger(__name__)


class MainWindow(QMainWindow, Ui_MainWindow):
    """Builds and updates a PyQt6 GUI."""

    def __init__(self) -> None:
        """Initialize the GUI.

        Build the GUI from XML, connects signals and slots, and prescribes GUI behaviors that are
        either unavailable through Qt Designer (e.g., matching values between widgets and config
        file settings or setting plot background colors) or are easier to manage in this way
        (e.g., changing style sheets and flexible table column widths).
        """
        super().__init__()

        self.build_gui()
        self.manage_threadpool()
        self.get_runtime_info()
        self.load_user_config()
        self.connect_widget_signals()
        self.connect_signal_proxies()
        self.prepare_dialogs()
        self.prepare_plots()
        self.prepare_models()
        self.register_resources()
        self.register_shortcuts()
        self.schedule_events()
        self.check_for_updates()

        if running_from_exe():
            pyi_splash.close()

    def closeEvent(self, event) -> None:
        """Attempt safer cleanup before closing main window."""
        if self.pool.activeThreadCount() != 0:
            logger.warning("Close event called with active file reads!")
            self.pool.clear()
        update_metadata_file()
        return super().closeEvent(event)

    @stopwatch(silent=True)
    def build_gui(self) -> None:
        """Build main window from .ui file and connect GUI logger to plaintext field."""
        self.setupUi(self)

        # Define default states for GUI elements
        self.view_tabs.setCurrentIndex(Tab.Line.value)
        self.show_data_source_groups(Tab.Line.value)
        self.btn_reset_legend_position.setHidden(True)
        self.check_show_file_filters.setChecked(False)

        # Track current tab index
        self.view_tabs.currentChanged.connect(self.changed_current_tab)

        # Hide development/experimental options group when running from frozen exe. Widgets inside
        # this group should not have their slots connected to ensure consistent behavior. Values
        # exposed through the configuration file will always serve the default value.
        if running_from_exe():
            self.group_settings_development.setHidden(True)

        # Set up progress bar
        self.reset_progress_bar()

        # Create GUI logger handle
        gui_log: GUILogger = GUILogger(self.update_gui_log)
        getLogger().addHandler(gui_log)
        log_chapter(logger, "Startup")

    @stopwatch(silent=True)
    def manage_threadpool(self) -> None:
        """Set up the thread pool and related variables for I/O processing."""
        if running_from_exe():
            pyi_splash.update_text("Managing threadpool...")

        self.pool: QThreadPool = QThreadPool().globalInstance()
        self.pool.setMaxThreadCount(int(setting("General", "MaxIOThreads")))

        # Vars for tracking file processing time
        self.batch_count: int = 0
        self.batch_size: int = 0
        self.batch_time: int = 0

    @stopwatch(silent=True)
    def get_runtime_info(self) -> None:
        """Get the application's base path. This is used for relative paths with icons and QSS."""
        if running_from_exe():
            pyi_splash.update_text("Gathering runtime info...")

        self.base_path: str = app_root()

        logger.debug(
            f"Running from {'frozen' if running_from_exe() else 'normal'} environment - "
            f"unhandled exceptions will {'' if running_from_exe() else 'NOT '}be suppressed"
        )

    @stopwatch(silent=True)
    def load_user_config(self) -> None:
        """Set and connect widgets with their respective configuration values."""
        if running_from_exe():
            pyi_splash.update_text("Importing user config...")

        try:
            self.general_config_options()
            self.plotting_config_options()
            self.crosshair_config_options()
            self.line_config_options()
            self.percentile_config_options()
            self.histogram_config_options()
            self.box_config_options()
            self.scatter_config_options()
            self.experience_config_options()
            self.stutter_config_options()
            self.oscillation_config_options()
            self.battery_config_options()
            self.exporting_config_options()
            self.logging_config_options()
            self.metadata_config_options()
            # self.statistics_config_options()  # Managed by gui.dialogs.stat_metrics

            if not running_from_exe():
                self.development_config_options()

            # Enable/disable widgets based on field values
            self.combo_use_downsampling.currentTextChanged.connect(
                lambda: self.spin_sample_rate.setEnabled(
                    self.combo_use_downsampling.currentText() == "Static"
                )
            )
            self.combo_use_antialiasing.setDisabled(self.combo_renderer.currentText() == "OpenGL")
        except ValueError:
            if running_from_exe():
                pyi_splash.close()

            QMessageBox.information(
                self,
                "Unexpected Configuration Error",
                "Configuration file could not be read. Default settings were restored.",
            )
            logger.error("Config file may be outdated or corrupted")
            self.reset_config_settings()
        except Exception as e:
            log_exception(logger, e)

    def general_config_options(self, sect: str = "General") -> None:
        """Set and connect general configuration options."""
        self.btn_toggle_css.setChecked(setting_bool(sect, "UseDarkStylesheet"))
        self.combo_line_time_scale.setCurrentText(setting(sect, "TimeScale"))
        self.combo_stats_time_scale.setCurrentText(setting(sect, "TimeScale"))
        self.check_diminish_fallbacks.setChecked(setting_bool(sect, "DiminishFallbacks"))
        self.spin_max_threads.setValue(int(setting(sect, "MaxIOThreads")))
        self.combo_drop_na_cols.setCurrentText(str(setting_bool(sect, "DropNAColumns")))
        self.spin_compress_size.setValue(int(setting(sect, "CompressionMinSizeMB")))
        self.spin_decimal_places.setValue(int(setting(sect, "DecimalPlaces")))

        self.spin_max_threads.valueChanged.connect(lambda x: set_value(sect, "MaxIOThreads", x))
        self.combo_line_time_scale.currentTextChanged.connect(
            lambda x: set_value(sect, "TimeScale", x)
        )
        self.combo_stats_time_scale.currentTextChanged.connect(
            lambda x: set_value(sect, "TimeScale", x)
        )
        self.check_diminish_fallbacks.clicked.connect(
            lambda x: set_value(sect, "DiminishFallbacks", x)
        )
        self.combo_drop_na_cols.currentTextChanged.connect(
            lambda x: set_value(sect, "DropNAColumns", x)
        )
        self.spin_compress_size.valueChanged.connect(
            lambda x: set_value(sect, "CompressionMinSizeMB", x)
        )
        self.spin_decimal_places.valueChanged.connect(lambda x: set_value(sect, "DecimalPlaces", x))

    def plotting_config_options(self, sect: str = "Plotting") -> None:
        """Set and connect configuration options for general plotting."""
        self.combo_renderer.setCurrentText(setting(sect, "Renderer"))
        self.combo_use_antialiasing.setCurrentText(setting(sect, "Antialiasing"))
        self.combo_plot_empty_data.setCurrentText(str(setting_bool(sect, "PlotEmptyData")))
        self.spin_normal_alpha.setValue(int(setting(sect, "NormalAlpha")))
        self.spin_emphasized_alpha.setValue(int(setting(sect, "EmphasizedAlpha")))
        self.spin_diminished_alpha.setValue(int(setting(sect, "DiminishedAlpha")))
        self.spin_axis_label_size.setValue(int(setting(sect, "AxisLabelFontSize")))
        self.spin_tick_text_offset.setValue(int(setting(sect, "AxisLabelOffset")))
        self.spin_axis_tick_length.setValue(int(setting(sect, "AxisTickLength")))
        self.spin_main_title_size.setValue(int(setting(sect, "MainTitleFontSize")))
        self.line_main_title.setText(setting(sect, "MainTitleFormat"))
        self.line_legend_item.setText(setting(sect, "LegendItemFormat"))
        self.spin_legend_font_size.setValue(int(setting(sect, "LegendItemFontSize")))

        self.combo_renderer.currentTextChanged.connect(lambda x: set_value(sect, "Renderer", x))
        self.combo_use_antialiasing.currentTextChanged.connect(
            lambda x: set_value(sect, "Antialiasing", x)
        )
        self.combo_plot_empty_data.currentTextChanged.connect(
            lambda x: set_value(sect, "PlotEmptyData", x)
        )
        self.spin_normal_alpha.valueChanged.connect(lambda x: set_value(sect, "NormalAlpha", x))
        self.spin_emphasized_alpha.valueChanged.connect(
            lambda x: set_value(sect, "EmphasizedAlpha", x)
        )
        self.spin_diminished_alpha.valueChanged.connect(
            lambda x: set_value(sect, "DiminishedAlpha", x)
        )
        self.spin_axis_label_size.valueChanged.connect(
            lambda x: set_value(sect, "AxisLabelFontSize", x)
        )
        self.spin_tick_text_offset.valueChanged.connect(
            lambda x: set_value(sect, "AxisLabelOffset", x)
        )
        self.spin_axis_tick_length.valueChanged.connect(
            lambda x: set_value(sect, "AxisTickLength", x)
        )
        self.spin_main_title_size.valueChanged.connect(
            lambda x: set_value(sect, "MainTitleFontSize", x)
        )
        self.line_main_title.textChanged.connect(lambda x: set_value(sect, "MainTitleFormat", x))
        self.line_legend_item.textChanged.connect(lambda x: set_value(sect, "LegendItemFormat", x))
        self.spin_legend_font_size.valueChanged.connect(
            lambda x: set_value(sect, "LegendItemFontSize", x)
        )

    def crosshair_config_options(self, sect: str = "Crosshair") -> None:
        """Set and connect configuration options for the crosshair cursor."""
        self.spin_crosshair_update_rate.setValue(int(setting(sect, "CursorUpdateRate")))
        self.combo_use_downsampling.setCurrentText(str(setting(sect, "UseDownsampling")))
        self.spin_sample_rate.setValue(int(setting(sect, "SampleRate")))
        self.spin_sample_rate.setEnabled(setting(sect, "UseDownsampling") == "Static")

        self.spin_crosshair_update_rate.valueChanged.connect(
            lambda x: set_value(sect, "CursorUpdateRate", x)
        )
        self.combo_use_downsampling.currentTextChanged.connect(
            lambda x: set_value(sect, "UseDownsampling", x)
        )
        self.spin_sample_rate.valueChanged.connect(lambda x: set_value(sect, "SampleRate", x))

    def line_config_options(self, sect: str = "Line") -> None:
        """Set and connect configuration options for the line plot."""
        self.check_clamp_x_min.setChecked(setting_bool(sect, "ClampXMinimum"))
        self.check_clamp_y_min.setChecked(setting_bool(sect, "ClampYMinimum"))

        self.check_clamp_x_min.clicked.connect(lambda x: set_value(sect, "ClampXMinimum", x))
        self.check_clamp_y_min.clicked.connect(lambda x: set_value(sect, "ClampYMinimum", x))

    def percentile_config_options(self, sect: str = "Percentiles") -> None:
        """Set and connect configuration options for the percentile plot."""
        self.check_clamp_percentiles_y_min.setChecked(setting_bool(sect, "ClampYMinimum"))
        self.spin_percentile_start.setValue(float(setting(sect, "PercentileStart")))
        self.spin_percentile_end.setValue(float(setting(sect, "PercentileEnd")))
        self.spin_percentile_step.setValue(float(setting(sect, "PercentileStep")))
        self.update_percentile_steps(refresh=False)

        self.check_clamp_percentiles_y_min.clicked.connect(
            lambda x: set_value(sect, "ClampYMinimum", x)
        )
        self.spin_percentile_start.valueChanged.connect(
            lambda x: set_value(sect, "PercentileStart", x)
        )
        self.spin_percentile_end.valueChanged.connect(lambda x: set_value(sect, "PercentileEnd", x))
        self.spin_percentile_step.valueChanged.connect(
            lambda x: set_value(sect, "PercentileStep", x)
        )

    def histogram_config_options(self, sect: str = "Histogram") -> None:
        """Set and connect configuration options for the histogram plot."""
        self.check_clamp_histogram_x_min.setChecked(setting_bool(sect, "ClampXMinimum"))
        self.check_clamp_histogram_y_min.setChecked(setting_bool(sect, "ClampYMinimum"))
        self.spin_histogram_bins.setValue(int(setting(sect, "HistogramBinSize")))

        self.check_clamp_histogram_x_min.clicked.connect(
            lambda x: set_value(sect, "ClampXMinimum", x)
        )
        self.check_clamp_histogram_y_min.clicked.connect(
            lambda x: set_value(sect, "ClampYMinimum", x)
        )
        self.spin_histogram_bins.valueChanged.connect(
            lambda x: set_value(sect, "HistogramBinSize", x)
        )

    def box_config_options(self, sect: str = "Box") -> None:
        """Set and connect configuration options for the box plot."""
        self.check_clamp_box_x_min.setChecked(setting_bool(sect, "ClampXMinimum"))
        self.check_clamp_box_y_min.setChecked(setting_bool(sect, "ClampYMinimum"))
        self.check_box_hide_legend.setChecked(setting_bool(sect, "HideLegend"))
        self.combo_box_plot_outliers.setCurrentText(setting(sect, "OutlierValues"))
        self.spin_box_height.setValue(int(setting(sect, "Height")))
        self.spin_box_spacing.setValue(int(setting(sect, "Spacing")))

        self.check_clamp_box_x_min.clicked.connect(lambda x: set_value(sect, "ClampXMinimum", x))
        self.check_clamp_box_y_min.clicked.connect(lambda x: set_value(sect, "ClampYMinimum", x))
        self.check_box_hide_legend.clicked.connect(lambda x: set_value(sect, "HideLegend", x))
        self.combo_box_plot_outliers.currentTextChanged.connect(
            lambda x: set_value(sect, "OutlierValues", x)
        )
        self.spin_box_height.valueChanged.connect(lambda x: set_value(sect, "Height", x))
        self.spin_box_spacing.valueChanged.connect(lambda x: set_value(sect, "Spacing", x))

    def scatter_config_options(self, sect: str = "Scatter") -> None:
        """Set and connect configuration options for the scatter plot."""
        self.check_clamp_scatter_x_min.setChecked(setting_bool(sect, "ClampXMinimum"))
        self.check_clamp_scatter_y_min.setChecked(setting_bool(sect, "ClampYMinimum"))

        self.check_clamp_scatter_x_min.clicked.connect(
            lambda x: set_value(sect, "ClampXMinimum", x)
        )
        self.check_clamp_scatter_y_min.clicked.connect(
            lambda x: set_value(sect, "ClampYMinimum", x)
        )

    def experience_config_options(self, sect: str = "Experience") -> None:
        """Set and connect configuration options for the experience plot."""
        self.spin_experience_callout_size.setValue(int(setting(sect, "CalloutTextSize")))
        self.check_experience_hide_legend.setChecked(setting_bool(sect, "HideLegend"))
        self.spin_experience_height.setValue(int(setting(sect, "Height")))
        self.spin_experience_spacing.setValue(int(setting(sect, "Spacing")))

        self.spin_experience_callout_size.valueChanged.connect(
            lambda x: set_value(sect, "CalloutTextSize", x)
        )
        self.check_experience_hide_legend.clicked.connect(
            lambda x: set_value(sect, "HideLegend", x)
        )
        self.spin_experience_height.valueChanged.connect(lambda x: set_value(sect, "Height", x))
        self.spin_experience_spacing.valueChanged.connect(lambda x: set_value(sect, "Spacing", x))

    def stutter_config_options(self, sect: str = "StutterHeuristic") -> None:
        """Set and connect configuration options for stutter heuristics."""
        self.spin_stutter_delta_ms.setValue(float(setting(sect, "StutterDeltaMs")))
        self.spin_stutter_delta_pct.setValue(float(setting(sect, "StutterDeltaPct")))
        self.spin_stutter_window_size.setValue(int(setting(sect, "StutterWindowSize")))
        self.spin_stutter_warn_pct.setValue(float(setting(sect, "StutterWarnPct")))
        self.spin_stutter_warn_avg.setValue(float(setting(sect, "StutterWarnAvg")))
        self.spin_stutter_warn_max.setValue(float(setting(sect, "StutterWarnMax")))

        self.spin_stutter_delta_ms.valueChanged.connect(
            lambda x: set_value(sect, "StutterDeltaMs", x)
        )
        self.spin_stutter_delta_pct.valueChanged.connect(
            lambda x: set_value(sect, "StutterDeltaPct", x)
        )
        self.spin_stutter_window_size.valueChanged.connect(
            lambda x: set_value(sect, "StutterWindowSize", x)
        )
        self.spin_stutter_warn_pct.valueChanged.connect(
            lambda x: set_value(sect, "StutterWarnPct", x)
        )
        self.spin_stutter_warn_avg.valueChanged.connect(
            lambda x: set_value(sect, "StutterWarnAvg", x)
        )
        self.spin_stutter_warn_max.valueChanged.connect(
            lambda x: set_value(sect, "StutterWarnMax", x)
        )

    def oscillation_config_options(self, sect: str = "OscillationHeuristic") -> None:
        """Set and connect configuration options for oscillation heuristics."""
        self.group_settings_oscillation.setChecked(setting_bool(sect, "TestForOscillation"))
        self.spin_osc_delta_ms.setValue(float(setting(sect, "OscDeltaMs")))
        self.spin_osc_delta_pct.setValue(float(setting(sect, "OscDeltaPct")))
        self.spin_osc_warn_pct.setValue(float(setting(sect, "OscWarnPct")))

        self.group_settings_oscillation.clicked.connect(
            lambda x: set_value(sect, "TestForOscillation", x)
        )
        self.group_settings_oscillation.clicked.connect(self.update_stutter_parameters)
        self.spin_osc_delta_ms.valueChanged.connect(lambda x: set_value(sect, "OscDeltaMs", x))
        self.spin_osc_delta_pct.valueChanged.connect(lambda x: set_value(sect, "OscDeltaPct", x))
        self.spin_osc_warn_pct.valueChanged.connect(lambda x: set_value(sect, "OscWarnPct", x))

    def battery_config_options(self, sect: str = "BatteryLife") -> None:
        """Set and connect configuration options for battery life projection."""
        self.spin_battery_max_level.setValue(int(setting(sect, "BatteryMaxLevel")))
        self.spin_battery_min_level.setValue(int(setting(sect, "BatteryMinLevel")))

        self.spin_battery_max_level.valueChanged.connect(
            lambda x: set_value(sect, "BatteryMaxLevel", x)
        )
        self.spin_battery_min_level.valueChanged.connect(
            lambda x: set_value(sect, "BatteryMinLevel", x)
        )

    def exporting_config_options(self, sect: str = "Exporting") -> None:
        """Set and connect configuration options for data export."""
        self.line_exporting_path.setText(setting(sect, "SavePath"))
        self.combo_image_format.setCurrentText(setting(sect, "ImageFormat"))

        self.line_exporting_path.textChanged.connect(lambda x: set_value(sect, "SavePath", x))
        self.combo_image_format.currentTextChanged.connect(
            lambda x: set_value(sect, "ImageFormat", x)
        )

    def logging_config_options(self, sect: str = "Logger") -> None:
        """Set and connect configuration options for the logging environment."""
        self.line_logging_path.setText(setting(sect, "LoggingPath"))
        self.spin_log_max_number.setValue(int(setting(sect, "MaxFiles")))

        self.line_logging_path.textChanged.connect(lambda x: set_value(sect, "LoggingPath", x))
        self.spin_log_max_number.valueChanged.connect(lambda x: set_value(sect, "MaxFiles", x))

    def metadata_config_options(self, sect: str = "Metadata") -> None:
        """Set and connect configuration options for file metadata."""
        self.spin_metadata_expiration.setValue(int(setting(sect, "ExpirationTime")))

        self.spin_metadata_expiration.valueChanged.connect(
            lambda x: set_value(sect, "ExpirationTime", x)
        )

    def development_config_options(self, sect: str = "Development") -> None:
        """Set and connect configuration options for development parameters."""
        self.spin_stopwatch_conf_interval.setValue(float(setting(sect, "StopwatchCI")))
        self.spin_stopwatch_std_err_target.setValue(float(setting(sect, "StopwatchStdError")))
        self.spin_dev_signal_rate.setValue(int(setting(sect, "SignalProxyRate")))
        self.spin_stopwatch_loop_timeout.setValue(int(setting(sect, "StopwatchTimeLimit")))
        self.combo_timekeeper_key.setCurrentText(setting(sect, "TimekeeperKey"))

        self.spin_stopwatch_conf_interval.valueChanged.connect(
            lambda x: set_value(sect, "StopwatchCI", x)
        )
        self.spin_stopwatch_std_err_target.valueChanged.connect(
            lambda x: set_value(sect, "StopwatchStdError", x)
        )
        self.spin_dev_signal_rate.valueChanged.connect(
            lambda x: set_value(sect, "SignalProxyRate", x)
        )
        self.spin_stopwatch_loop_timeout.valueChanged.connect(
            lambda x: set_value(sect, "StopwatchTimeLimit", x)
        )
        self.combo_timekeeper_key.currentTextChanged.connect(
            lambda x: set_value(sect, "TimekeeperKey", x)
        )

    @stopwatch(silent=True)
    def connect_widget_signals(self) -> None:
        """Connect GUI widgets to functions.

        Not all GUI widget signals are connected here; some are connected from within layout.ui
        while others are connected through signal proxies (see `connect_signal_proxies()`). GUI
        widget signals are emitted in the approximate order of definition: layout.ui first, then
        those defined here, and then those regulated by signal proxies.

        Functions connected here must be able to tolerate a large number of event signals without
        disrupting the user experience. If the function benefits from a moderated signal rate, it
        should be connected through `connect_signal_proxies()` instead.
        """
        if running_from_exe():
            pyi_splash.update_text("Connecting signals...")

        # Push buttons
        self.btn_import_file.clicked.connect(self.add_files)
        self.btn_import_folder.clicked.connect(self.add_folder)
        self.btn_remove_all_files.clicked.connect(self.remove_all_files)
        self.btn_plot_selected_files.clicked.connect(self.plot_selected_files)
        self.btn_plot_all_files.clicked.connect(self.plot_all_files)
        self.btn_clear_plots.clicked.connect(
            lambda: self.clear_plots(
                QApplication.keyboardModifiers() == Qt.KeyboardModifier.ShiftModifier
            )
        )
        self.btn_choose_stats.clicked.connect(self.choose_stats)
        # self.btn_multiplot_settings.clicked.connect(self.manage_line_plot_axes)
        self.btn_settings_default.clicked.connect(self.prompt_for_config_reset)
        self.btn_reset_legend_position.clicked.connect(self.reset_legend_position)
        self.btn_open_log_folder.clicked.connect(self.open_log_folder)
        self.btn_open_output_folder.clicked.connect(self.open_output_folder)
        self.btn_export_stats.clicked.connect(self.export_stats)
        self.btn_export_view.clicked.connect(self.export_browser_view)
        self.btn_pick_exporting_path.clicked.connect(self.change_export_path)
        self.btn_pick_logging_path.clicked.connect(self.change_logging_path)
        self.btn_toggle_css.toggled.connect(self.apply_stylesheet)
        self.btn_swap_sources.clicked.connect(self.swap_data_sources)

        # Checkboxes
        self.check_valid_files_only.toggled.connect(
            lambda x: self.filter_loaded_files(False, "Invalid", "x" if x else x)  # Workaround
        )
        self.check_enable_scatter.toggled.connect(self.toggle_scatter_plot)
        self.check_clamp_x_min.clicked.connect(lambda: self.clamp_axis("Line", "x"))
        self.check_clamp_histogram_x_min.clicked.connect(lambda: self.clamp_axis("Histogram", "x"))
        self.check_clamp_box_x_min.clicked.connect(lambda: self.clamp_axis("Box", "x"))
        self.check_clamp_scatter_x_min.clicked.connect(lambda: self.clamp_axis("Scatter", "x"))
        self.check_clamp_y_min.clicked.connect(lambda: self.clamp_axis("Line", "y"))
        self.check_clamp_percentiles_y_min.clicked.connect(
            lambda: self.clamp_axis("Percentiles", "y")
        )
        self.check_clamp_histogram_y_min.clicked.connect(lambda: self.clamp_axis("Histogram", "y"))
        self.check_clamp_box_y_min.clicked.connect(lambda: self.clamp_axis("Box", "y"))
        self.check_box_hide_legend.toggled.connect(
            lambda: self.plots["Box"].viewbox.legend.toggle()
        )
        self.check_box_show_outliers.clicked.connect(self.toggle_outliers)
        self.check_clamp_scatter_y_min.clicked.connect(lambda: self.clamp_axis("Scatter", "y"))
        self.check_experience_hide_legend.toggled.connect(
            lambda: self.plots["Experience"].viewbox.legend.toggle()
        )
        self.check_diminish_fallbacks.clicked.connect(lambda: self.table_stats.viewport().update())
        self.check_gridlines_horizontal.clicked.connect(self.update_gridlines)
        self.check_gridlines_vertical.clicked.connect(self.update_gridlines)

        # Combo boxes
        self.combo_file_text_format.currentTextChanged.connect(self.change_file_list_format)
        self.combo_plot_empty_data.currentTextChanged.connect(self.refresh_plots)
        self.combo_box_plot_outliers.currentTextChanged.connect(self.refresh_plots)
        self.combo_primary_source.currentTextChanged.connect(self.update_primary_source)
        self.combo_secondary_source.currentTextChanged.connect(self.update_secondary_source)
        self.combo_stats_compare_against.currentTextChanged.connect(self.compare_against_file)
        self.combo_browse_file.currentTextChanged.connect(self.update_browser_files)
        self.combo_browse_file.currentTextChanged.connect(self.update_browser_headers)
        self.combo_browse_header.currentTextChanged.connect(self.browse_by_header)
        self.combo_use_downsampling.currentTextChanged.connect(self.pyqtgraph_line.redraw_crosshair)
        self.combo_line_time_scale.currentTextChanged.connect(self.update_dynamic_headers)
        self.combo_stats_time_scale.currentTextChanged.connect(self.update_dynamic_headers)

        # Line edit boxes (text fields)
        self.line_browse_expression.textChanged.connect(self.browse_by_expression)
        self.line_main_title.textChanged.connect(self.translate_plot_titles)
        self.line_legend_item.textEdited.connect(self.update_legend_labels)
        self.spin_legend_font_size.valueChanged.connect(self.refresh_plots)
        self.line_filter_include_type.textChanged.connect(
            lambda x: self.filter_loaded_files(True, "Capture Type", x)
        )
        self.line_filter_exclude_type.textChanged.connect(
            lambda x: self.filter_loaded_files(False, "Capture Type", x)
        )
        self.line_filter_include_application.textChanged.connect(
            lambda x: self.filter_loaded_files(True, "Application", x)
        )
        self.line_filter_exclude_application.textChanged.connect(
            lambda x: self.filter_loaded_files(False, "Application", x)
        )
        self.line_filter_include_resolution.textChanged.connect(
            lambda x: self.filter_loaded_files(True, "Resolution", x)
        )
        self.line_filter_exclude_resolution.textChanged.connect(
            lambda x: self.filter_loaded_files(False, "Resolution", x)
        )
        self.line_filter_include_runtime.textChanged.connect(
            lambda x: self.filter_loaded_files(True, "Runtime", x)
        )
        self.line_filter_exclude_runtime.textChanged.connect(
            lambda x: self.filter_loaded_files(False, "Runtime", x)
        )
        self.line_filter_include_gpu.textChanged.connect(
            lambda x: self.filter_loaded_files(True, "GPU", x)
        )
        self.line_filter_exclude_gpu.textChanged.connect(
            lambda x: self.filter_loaded_files(False, "GPU", x)
        )
        self.line_filter_include_filename.textChanged.connect(
            lambda x: self.filter_loaded_files(True, "File Name", x)
        )
        self.line_filter_exclude_filename.textChanged.connect(
            lambda x: self.filter_loaded_files(False, "File Name", x)
        )

        # Spinner boxes
        self.spin_normal_alpha.valueChanged.connect(PlotObject.adjust_alpha_by_selection)
        self.spin_normal_alpha.valueChanged.connect(PlotObject.update_pen_alpha_values)
        self.spin_emphasized_alpha.valueChanged.connect(PlotObject.adjust_alpha_by_selection)
        self.spin_diminished_alpha.valueChanged.connect(PlotObject.adjust_alpha_by_selection)
        self.spin_axis_label_size.valueChanged.connect(self.translate_axis_labels)
        self.spin_main_title_size.valueChanged.connect(self.translate_plot_titles)
        self.spin_crosshair_update_rate.valueChanged.connect(self.pyqtgraph_line.redraw_crosshair)
        self.spin_crosshair_update_rate.editingFinished.connect(
            self.pyqtgraph_line.redraw_crosshair
        )
        self.spin_battery_max_level.valueChanged.connect(self.recalculate_time_stats)
        self.spin_battery_min_level.valueChanged.connect(self.recalculate_time_stats)
        self.spin_sample_rate.valueChanged.connect(self.pyqtgraph_line.redraw_crosshair)
        self.spin_sample_rate.editingFinished.connect(self.pyqtgraph_line.redraw_crosshair)
        self.spin_axis_tick_length.valueChanged.connect(self.adjust_plot_axes_styles)
        self.spin_tick_text_offset.valueChanged.connect(self.adjust_plot_axes_styles)
        self.spin_gridline_opacity.valueChanged.connect(self.update_gridlines)
        self.spin_decimal_places.valueChanged.connect(self.refresh_stats)
        self.spin_decimal_places.valueChanged.connect(self.order_experience_plots)

        # Menu bar actions
        self.menu_file_exit.triggered.connect(self.close)
        self.menu_metadata_remove_properties.triggered.connect(lambda: remove_section("Properties"))
        self.menu_metadata_remove_color.triggered.connect(lambda: remove_section("Color"))
        self.menu_metadata_remove_time.triggered.connect(lambda: remove_section("Time"))
        self.menu_metadata_remove_all.triggered.connect(remove_all_records)
        self.menu_about_shortcuts.triggered.connect(lambda: HelpShortcutsDialog().exec())
        self.menu_about_github.triggered.connect(
            lambda: open_browser("https://github.com/Dolikhena/Pydra")
        )

        # Connect to signal-emitting objects located in other Pydra modules
        ContextSignal.emitter.signal.connect(self.context_menu_signals)
        SquareLegendItem.clicked.signal.connect(self.legend_was_clicked)
        SquareLegendItem.dragged.signal.connect(
            lambda: self.btn_reset_legend_position.setVisible(True)
        )
        SquareLegendItem.time_reset.signal.connect(self.refresh_plots)
        SquareLegendItem.view_file.signal.connect(self.view_selected_file)
        SquareLegendItem.view_properties.signal.connect(self.view_file_properties)

    @stopwatch(silent=True)
    def connect_signal_proxies(self) -> None:
        """Regulate the frequency of some signals using a proxy.

        Widgets that are connected to functions with long execution times or have cascade potential
        (e.g., quickly changing values from a spinner box) can be moderated by using a signal proxy,
        which limits the amount and/or frequency of signals that a widget can emit per second. For
        example, making rapid adjustments to the spinner widgets associated with stutter heuristics
        would lead to wasteful and expensive recalculations, so limiting the signal rates of these
        widgets improves the user experience.
        """
        if running_from_exe():
            pyi_splash.update_text("Connecting proxies...")

        signal_batch: tuple
        self.proxies: list = []
        proxy = SignalProxy
        signals_per_second: int = int(setting("Development", "SignalProxyRate"))

        def batch_connections(signals: tuple, slot: Callable) -> list:
            """Return a batched list of connected signals and slots."""
            return [
                proxy(signal.valueChanged, rateLimit=signals_per_second, slot=slot)
                for signal in signals
            ]

        # Line plot widgets
        signal_batch = (self.spin_x_min, self.spin_x_max, self.spin_y_min, self.spin_y_max)
        self.proxies += batch_connections(signal_batch, lambda: self.change_range("Line"))

        # Percentile plot axis widgets
        signal_batch = (self.spin_percentiles_y_min, self.spin_percentiles_y_max)
        self.proxies += batch_connections(signal_batch, lambda: self.change_range("Percentiles"))

        # Percentile plot range/step widgets
        signal_batch = (
            self.spin_percentile_start,
            self.spin_percentile_end,
            self.spin_percentile_step,
        )
        self.proxies += batch_connections(signal_batch, self.update_percentile_steps)

        # Percentile plot widgets
        self.proxies += [
            SignalProxy(
                self.spin_histogram_bins.valueChanged,
                rateLimit=signals_per_second,
                slot=self.refresh_plots,
            )
        ]

        # Histogram plot widgets
        signal_batch = (
            self.spin_histogram_x_min,
            self.spin_histogram_x_max,
            self.spin_histogram_y_min,
            self.spin_histogram_y_max,
        )
        self.proxies += batch_connections(signal_batch, lambda: self.change_range("Histogram"))

        # Box plot widgets
        signal_batch = (
            self.spin_box_x_min,
            self.spin_box_x_max,
            self.spin_box_y_min,
            self.spin_box_y_max,
        )
        self.proxies += batch_connections(signal_batch, lambda: self.change_range("Box"))
        signal_batch = (self.spin_box_height, self.spin_box_spacing)
        self.proxies += batch_connections(signal_batch, lambda: self.order_box_plots())

        # Scatter plot widgets
        signal_batch = (
            self.spin_scatter_x_min,
            self.spin_scatter_x_max,
            self.spin_scatter_y_min,
            self.spin_scatter_y_max,
        )
        self.proxies += batch_connections(signal_batch, lambda: self.change_range("Scatter"))

        # Experience plot widgets
        signal_batch = (
            self.spin_experience_x_min,
            self.spin_experience_x_max,
            self.spin_experience_y_min,
            self.spin_experience_y_max,
        )
        self.proxies += batch_connections(signal_batch, lambda: self.change_range("Experience"))
        signal_batch = (
            self.spin_experience_callout_size,
            self.spin_experience_height,
            self.spin_experience_spacing,
        )
        self.proxies += batch_connections(signal_batch, self.order_experience_plots)

        # Stutter parameters
        signal_batch = (
            self.spin_stutter_delta_ms,
            self.spin_stutter_delta_pct,
            self.spin_stutter_window_size,
            self.spin_stutter_warn_pct,
            self.spin_stutter_warn_avg,
            self.spin_stutter_warn_max,
        )
        self.proxies += batch_connections(signal_batch, self.update_stutter_parameters)

        # Oscillation parameters
        signal_batch = (
            self.spin_osc_delta_ms,
            self.spin_osc_delta_pct,
            self.spin_osc_warn_pct,
        )
        self.proxies += batch_connections(signal_batch, self.update_stutter_parameters)

    @stopwatch(silent=True)
    def prepare_plots(self) -> None:
        """Define the initial state of the plot widgets."""
        if running_from_exe():
            pyi_splash.update_text("Preparing plots...")

        setConfigOptions(
            antialias=(setting("Plotting", "Antialiasing") == "Enabled"),
            mouseRateLimit=0,  # Disable mouse rate limiting
            useNumba=True,
            segmentedLineMode="auto",  # improves perf with line thickness above 1 pixel
        )
        self.plots: dict[str, ContextMenuPlotWidget] = {
            "Line": self.pyqtgraph_line,
            "Percentiles": self.pyqtgraph_percentile,
            "Histogram": self.pyqtgraph_histogram,
            "Box": self.pyqtgraph_box,
            "Scatter": self.pyqtgraph_scatter,
            "Experience": self.pyqtgraph_experience,
        }

        ContextMenuPlotWidget.main_window = self
        for name, widget in self.plots.items():
            widget.set_name(name)  # Simplifies context menu handling

        # Associate plot-specific widgets for use in notifying the user when a plot with
        # a clamped axis contains (negative) values that are not visible while clamped.
        self.plot_range_controls = {
            "Line": {
                "x": (self.spin_x_min, self.spin_x_max, self.check_clamp_x_min, None),
                "y": (
                    self.spin_y_min,
                    self.spin_y_max,
                    self.check_clamp_y_min,
                    self.notice_label_negative_line_data,
                ),
            },
            "Percentiles": {
                "y": (
                    self.spin_percentiles_y_min,
                    self.spin_percentiles_y_max,
                    self.check_clamp_percentiles_y_min,
                    self.notice_label_negative_percentile_data,
                ),
            },
            "Histogram": {
                "x": (
                    self.spin_histogram_x_min,
                    self.spin_histogram_x_max,
                    self.check_clamp_histogram_x_min,
                    None,
                ),
                "y": (
                    self.spin_histogram_y_min,
                    self.spin_histogram_y_max,
                    self.check_clamp_histogram_y_min,
                    self.notice_label_negative_histogram_data,
                ),
            },
            "Box": {
                "x": (
                    self.spin_box_x_min,
                    self.spin_box_x_max,
                    self.check_clamp_box_x_min,
                    None,
                ),
                "y": (
                    self.spin_box_y_min,
                    self.spin_box_y_max,
                    self.check_clamp_box_y_min,
                    None,
                ),
            },
            "Scatter": {
                "x": (
                    self.spin_scatter_x_min,
                    self.spin_scatter_x_max,
                    self.check_clamp_scatter_x_min,
                    self.notice_label_negative_scatter_data_x,
                ),
                "y": (
                    self.spin_scatter_y_min,
                    self.spin_scatter_y_max,
                    self.check_clamp_scatter_y_min,
                    self.notice_label_negative_scatter_data_y,
                ),
            },
            "Experience": {
                "x": (
                    self.spin_experience_x_min,
                    self.spin_experience_x_max,
                    None,
                    None,
                ),
                "y": (
                    self.spin_experience_y_min,
                    self.spin_experience_y_max,
                    None,
                    None,
                ),
            },
        }

        # Hide range control widgets (for simplicity)
        for pairs in self.plot_range_controls.values():
            for widgets in pairs.values():
                min_widget, max_widget, _, _ = widgets
                min_widget.setVisible(False)
                max_widget.setVisible(False)

        # Route methods that adjust a plot's axes ranges through a signal proxy
        # Note that slot assignments must be explicit due to the use of lamdbas
        signals_per_second: int = int(setting("Development", "SignalProxyRate"))
        self.proxies += [
            SignalProxy(
                self.plots["Line"].sigRangeChanged,
                rateLimit=signals_per_second,
                slot=lambda: self.update_plot_ranges("Line"),
            ),
            SignalProxy(
                self.plots["Percentiles"].sigRangeChanged,
                rateLimit=signals_per_second,
                slot=lambda: self.update_plot_ranges("Percentiles"),
            ),
            SignalProxy(
                self.plots["Histogram"].sigRangeChanged,
                rateLimit=signals_per_second,
                slot=lambda: self.update_plot_ranges("Histogram"),
            ),
            SignalProxy(
                self.plots["Box"].sigRangeChanged,
                rateLimit=signals_per_second,
                slot=lambda: self.update_plot_ranges("Box"),
            ),
            SignalProxy(
                self.plots["Scatter"].sigRangeChanged,
                rateLimit=signals_per_second,
                slot=lambda: self.update_plot_ranges("Scatter"),
            ),
            SignalProxy(
                self.plots["Experience"].sigRangeChanged,
                rateLimit=signals_per_second,
                slot=lambda: self.update_plot_ranges("Experience"),
            ),
        ]

        self.functional_widgets: dict[str, tuple] = {
            "StutterDeltaMs": (self.spin_stutter_delta_ms, "QDoubleSpinBox", "StutterHeuristic"),
            "StutterDeltaPct": (self.spin_stutter_delta_pct, "QDoubleSpinBox", "StutterHeuristic"),
            "StutterWindowSize": (self.spin_stutter_window_size, "QSpinBox", "StutterHeuristic"),
            "OscDeltaMs": (self.spin_osc_delta_ms, "QDoubleSpinBox", "OscillationHeuristic"),
            "OscDeltaPct": (self.spin_osc_delta_pct, "QDoubleSpinBox", "OscillationHeuristic"),
        }

        # Prepare plot axes, titles, and related data models
        self.adjust_plot_axes_styles()
        self.warn_of_negative_values()
        self.warn_of_custom_values()
        self.reset_data_models()
        self.update_primary_source()
        self.translate_plot_titles()
        self.toggle_scatter_plot()

    @stopwatch(silent=True)
    def prepare_models(self) -> None:
        """Initialize data models and provide delegates where necessary.

        Item delegate are registered with stats table to attach behaviors to specific indexes, like
        only allowing mutable file properties to be changed or propagating changes to other selected
        rows within the same column. The associated PlotObject(s), their tooltips, plot titles, and
        legend items will also be updated with the new properties.
        """
        if running_from_exe():
            pyi_splash.update_text("Preparing models...")

        self.file_filter: dict[str, dict[bool, str]] = {True: {}, False: {}}
        self.header_visibility: dict[str, bool] = self.update_metric_visibility()
        self.table_headers: list[str] = stat_table_headers().values()
        self.set_data_source_models()

        self.delegate: SignalingDelegate = SignalingDelegate(self.table_stats)
        self.table_stats.setItemDelegate(self.delegate)
        self.table_stats.cell_edited.connect(self.update_properties)

    @stopwatch(silent=True)
    def register_resources(self) -> None:
        """Fetch and register icons, fonts, and style sheets used in the GUI."""
        if running_from_exe():
            pyi_splash.update_text("Registering resources...")

        self.integrity_icon: dict[str, object] = {
            "Initialized": icon_path("integrity-pending.png"),
            "Pending": icon_path("integrity-pending.png"),
            "Ideal": icon_path("integrity-ideal.png"),
            "Dirty": icon_path("integrity-dirty.png"),
            "Partial": icon_path("integrity-partial.png"),
            "Mangled": icon_path("integrity-mangled.png"),
            "Invalid": icon_path("integrity-invalid.png"),
        }

        use_dark_mode: bool = setting_bool("General", "UseDarkStylesheet")
        set_session_value("DarkMode", use_dark_mode)
        self.invalid_filter_expression: bool = False

        self.setWindowIcon(icon_path("pydra.ico"))
        self.apply_stylesheet(use_dark_mode)
        self.table_stats.resizeColumnsToContents()  # Resize after applying CSS
        self.btn_toggle_css.setChecked(use_dark_mode)

    @stopwatch(silent=True)
    def prepare_dialogs(self) -> None:
        """Define native file explorers and dialog window objects."""
        if running_from_exe():
            pyi_splash.update_text("Preparing dialogues...")

        self.file_extensions: tuple = (".csv", ".hml", ".txt")
        self.native_explorer_path: Path = Path(getenv("WINDIR")).joinpath("explorer.exe")

        self.file_dialog: QFileDialog = QFileDialog(self)
        self.metrics_dialog: QDialog = StatMetricsDialog(self)
        self.header_visibility: dict = {}

    @stopwatch(silent=True)
    def register_shortcuts(self) -> None:
        """Define key combinations and their associated functions."""
        line_vb = self.plots["Line"].viewbox

        # General UI
        QShortcut("F1", self).activated.connect(lambda: HelpShortcutsDialog().exec())
        QShortcut("Ctrl+S", self).activated.connect(self.export_current_view)

        # Plot items
        QShortcut("Ctrl+Backspace", self).activated.connect(
            lambda: self.clear_plots()
            if PlotObject.get_selected() is None
            else self.clear_selected_plot()
        )
        QShortcut("Ctrl+Left", self).activated.connect(
            lambda: line_vb.trim_plots(PlotObject.get_selected() is None, "Before")
        )
        QShortcut("Ctrl+Right", self).activated.connect(
            lambda: line_vb.trim_plots(PlotObject.get_selected() is None, "After")
        )
        QShortcut("Ctrl+Down", self).activated.connect(
            lambda: line_vb.zero_times(PlotObject.get_selected() is None)
        )
        QShortcut("Ctrl+Up", self).activated.connect(
            lambda: line_vb.reset_times(PlotObject.get_selected() is None)
        )

    @stopwatch(silent=True)
    def schedule_events(self) -> None:
        """Update labels for the number of busy I/O threads and current working set (memory usage)."""
        if running_from_exe():
            pyi_splash.update_text("Scheduling events...")

        self.process_mem_info: Callable = Process(getpid()).memory_info
        self.memalloc_tracker: Welford = Welford()

        self.timer: QTimer = QTimer()
        self.timer.setTimerType(Qt.TimerType.VeryCoarseTimer)
        self.timer.start(1000)
        self.timer.timeout.connect(self.update_activity_labels)

    @stopwatch(silent=True)
    def check_for_updates(self) -> None:
        """Check for updates and display a message if a newer version is available."""
        if running_from_exe():
            pyi_splash.update_text("Checking for updates...")

        def notify_of_update(results: tuple[bool, bool]) -> None:
            """Notify of a new version and ask to default the config settings."""
            update_is_available, config_out_of_date = results

            if update_is_available:
                StatusBarWithQueue.post("⭐️ A newer version of Pydra is available!")
            elif config_out_of_date:
                button = QMessageBox.StandardButton
                user_response = QMessageBox.question(
                    self,
                    "Pydra Configuration Update",
                    "Your configuration file belongs to an older version of Pydra."
                    "\nWould you like to use the default configuration?",
                    button.Yes | button.Ignore | button.No,
                    button.Yes,
                )

                if user_response == button.No:
                    return  # Asks again next time
                elif user_response == button.Yes:
                    self.reset_config_settings()
                elif user_response == button.Ignore:
                    set_value("General", "KeepOldConfig", "True")

                set_value("General", "Version", current_version_str())

        # Run on separate thread to avoid blocking the GUI
        worker = Worker(update_available)
        worker.signals.error.connect(lambda x: log_exception(logger, x))
        worker.signals.result.connect(notify_of_update)
        self.pool.start(worker.work)

    def report_memalloc_stats(self) -> None:
        """Report simple memory allocation statistics when the window is closed."""
        if self.memalloc_tracker.mean == 0:
            return

        report_table: dict[str, str] = {
            "Minimum": size_from_bytes(self.memalloc_tracker.min),
            "Average": size_from_bytes(self.memalloc_tracker.mean),
            "Maximum": size_from_bytes(self.memalloc_tracker.max),
        }
        log_table(logger, report_table, ("Metric", "Memalloc"))

    @pyqtSlot(int)
    def adjust_plot_axes_styles(self) -> None:
        """Update the bottom and left axes, usually in response to parameter changes."""
        tick_length: int = self.spin_axis_tick_length.value()
        tick_text_offset: int = self.spin_tick_text_offset.value()

        for plot in self.plots.values():
            bottom = plot.getAxis("bottom")
            left = plot.getAxis("left")

            bottom.enableAutoSIPrefix(enable=False)
            bottom.setStyle(
                tickLength=tick_length,
                tickTextOffset=tick_text_offset - 4,
                # stopAxisAtTick=(True, True),  # Throws errors with clamped axis
            )
            left.enableAutoSIPrefix(enable=False)
            left.setStyle(
                tickLength=tick_length,
                tickTextOffset=tick_text_offset,
                # stopAxisAtTick=(True, True),
            )

    @pyqtSlot(int)
    def context_menu_signals(self, signal_value: int = -1) -> Any:
        """Receive signals emitted from the subclassed pyqtgraph ViewBox class.

        Values are integers that correspond to Option enum struct defined in gui.contextsignals.
        This was chosen to reduce the number of signaller objects and connections between the GUI
        subclasses and the MainWindow instance.

        Args:
            * signal_value: Value corresponding to Option enum value.
        """
        signal_mapped_func: dict = {
            MenuOption.ToggleCursor.value: self.toggle_vertical_cursor,
            MenuOption.PlotDragged.value: self.update_dragged_line_plot,
            MenuOption.PlotDropped.value: self.update_dropped_line_plot,
            MenuOption.SelectFile.value: self.curve_was_clicked,
            MenuOption.ClearFile.value: self.clear_selected_plot,
            MenuOption.ClearAllFiles.value: self.clear_plots,
            MenuOption.ModifySelectedFile.value: self.modify_selected_plot,
            MenuOption.ModifyAllFiles.value: self.modify_all_plots,
            MenuOption.RefreshPlots.value: self.refresh_plots,
            MenuOption.ReorderLegend.value: self.reorder_legends,
            MenuOption.ViewInBrowser.value: self.view_selected_file,
            MenuOption.ViewProperties.value: self.view_file_properties,
        }.get(signal_value)
        return signal_mapped_func()

    @pyqtSlot(int)
    def changed_current_tab(self, idx: int) -> None:
        """Update current tab index and force specific plots to auto-range on first viewing."""
        set_session_value("CurrentTabIndex", idx)

        if idx == Tab.Experience.value:
            self.pyqtgraph_experience.force_autorange()

    @pyqtSlot(tuple)
    def legend_was_clicked(self, curve_and_callback: tuple[int, Callable]) -> None:
        """Select and emphasize the file whose legend item was just clicked."""
        try:
            curve, callback_func = curve_and_callback
            plot_obj = PlotObject.get_by_curve(curve)
            callback_func(plot_obj)
            self.curve_was_clicked()
        except Exception as e:
            log_exception(logger, e)

    @pyqtSlot(int)
    def toggle_vertical_cursor(self) -> None:
        """Show or hide the crosshair cursor on the Line plot."""
        crosshairs: bool = session("ShowCrosshairs")
        set_session_value("ShowCrosshairs", not crosshairs)

        if session("ShowCrosshairs"):
            self.plots["Line"].show_crosshair()
        else:
            self.plots["Line"].hide_crosshair()

    def update_activity_labels(self) -> None:
        """Update GUI labels with the number of active I/O threads and current working set.

        An INFO-level message will be logged and posted to the status bar if Pydra is using more
        than 10% of system memory.
        """
        # Memory allocation updates
        current_mem_alloc: float = self.process_mem_info().wset
        readable_mem_alloc: str = size_from_bytes(current_mem_alloc)

        self.memalloc_tracker.update(current_mem_alloc)
        self.label_mem_alloc.setText(f"<b>Working Set:</b> {readable_mem_alloc}")

        # Worker thread updates
        self.label_worker_threads.setText(
            f"<b>Active Threads:</b> {self.pool.activeThreadCount()} / {self.pool.maxThreadCount()}"
        )

    @pyqtSlot(QDragEnterEvent)
    def dragEnterEvent(self, drag_event: QDragEnterEvent) -> None:
        """Register when user drags a local file into the program area.

        Overloads MainWindow method to enable drag-and-drop file/folder importing.
        """
        if drag_event.mimeData().hasUrls():
            drag_event.accept()
        else:
            logger.info("Drag enter event was refused (remote, bad, or empty reference)")
            drag_event.ignore()

    @pyqtSlot(QDropEvent)
    def dropEvent(self, drop_event: QDropEvent) -> None:
        """Register drag-and-drop events for local files and folders.

        Overloads MainWindow method to enable drag-and-drop file/folder importing.
        """
        all_files: list
        num_folders: int

        # Discover local file URLs on root
        mime_data = drop_event.mimeData()
        dropped_urls: list[Path] = [Path(u.toLocalFile()) for u in mime_data.urls()]
        num_urls = len(dropped_urls)

        # Check local URLs for permitted extensions
        all_files = [
            f for f in dropped_urls if f.is_file() and f.suffix.lower() in self.file_extensions
        ]

        # Directory and subdirectory URLs
        dropped_folders: list = [f for f in dropped_urls if f.is_dir()]
        num_folders = len(dropped_folders)

        logger.debug(f"Received {num_urls:,} MIME object{'s' if num_urls == 1 else ''}")
        if (remote_urls := num_urls - len(all_files) - num_folders) > 0:
            logger.info(
                f"Skipped {remote_urls:,} remote reference{'s' if remote_urls == 1 else ''}"
            )

        if num_folders > 0:
            all_files = self.walk_through_directory(dropped_folders)

        self.batch_spawn_workers(all_files)

    def walk_through_directory(self, dropped_folders: list) -> list:
        """Discover nested files within a dropped directory."""
        all_files: list[str] = []
        # all_directories: list[str] = []
        num_folders: int = 0
        # root_depth: int = 0
        # root_dict: dict = {}
        # dir_level: int = 0

        for folder in dropped_folders:
            # root_depth = len(Path(folder).parents)
            for root, dirs, files in walk(folder):
                root = Path(root)

                # dir_level = len(root.parents) - root_depth
                # if dirs:
                #     root_dict[dir_level] = dirs

                num_folders += len(dirs)
                all_files += [
                    root / file
                    for file in files
                    if Path(file).suffix.lower() in self.file_extensions
                ]

        # for k, v in root_dict.items():
        #     print(f"{k}: {v}")

        logger.debug(
            f"Imported {len(all_files):,} total files in "
            f"{num_folders:,} folder{'s' if num_folders else ''}"
        )

        return all_files

    @pyqtSlot(str)
    def update_legend_labels(self, widget_text: str = "") -> None:
        """Change each legend item's label text in accordance with the newly prescribed format."""
        for plot_obj in PlotObject.valid_values():
            plot_obj.legend_name = plot_obj.translate_legend_name(widget_text)
            for plot, widget in self.plots.items():
                curve = plot_obj.curves[plot]
                if curve is None:
                    continue
                widget.viewbox.update_label(curve, plot_obj.formatted_legend())

            # Repeated updateSize() calls can eliminate or reduce the amount of whitespace that is
            # generated from suddenly removing a large amount of text from a legend item, like
            # when erasing the [FileName] or [FilePath] tags.
            SquareLegendItem.update_all()

        # Update plots where legend items are used for the axes
        self.order_box_plots(axis_only=True)
        self.order_experience_plots()

    @pyqtSlot(str)
    def change_file_list_format(self, fmt: str) -> None:
        """Adjust how loaded files appear in the left-hand list."""
        set_session_value("FileDisplayFormat", fmt)
        self.list_loaded_files.update_all_labels()

    @pyqtSlot(str, str, str)
    def update_properties(self, file_path: Path, property_name: str, new_value: str) -> None:
        """Update a file's mutable properties with user input from the stats table.

        Main plot titles, file tooltips, and legend names will be immediately updated.

        Args:
            * file_path (Path): File path, for looking up the related PlotObject.
            * property_name (str): The property being modified.
            * new_value (str): The updated value being assigned to the property.
        """
        if (plot_obj := PlotObject.get_by_path(file_path)) is None:
            return

        before = self.list_loaded_files.selectionModel()

        try:
            plot_obj.file.properties[property_name] = new_value
            plot_obj.set_capture_metrics()

            update_record(plot_obj.file.hash, plot_obj.file.properties)
            self.update_file_icon(file_path, plot_obj.file.integrity)  # Update tooltips

            self.update_legend_labels()
            self.translate_plot_titles()
        except Exception as e:
            logger.error(f"Failed to set {property_name} to {new_value} for {file_path}")
            log_exception(logger, e)

        self.list_loaded_files.setSelectionModel(before)

    def plotted_file_properties(self) -> list:
        """Return a list of properties for all currently plotted files."""
        return [v.file.properties for v in PlotObject.plotted_values()]

    def common_properties(self, property_name: str) -> str:
        """Find common properties shared between plotted captures for use with plot titles.

        Args:
            * property_name (str): Key to search from a PlotObject's file properties.

        Returns:
            * str: Name of the common property (or a suitable fallback) for all plotted files.
        """
        common_property: str = ""

        for file in self.plotted_file_properties():
            if not common_property:
                common_property = file[property_name]
            elif common_property != file[property_name]:
                common_property = (
                    f"Different {property_name}{'s' if property_name[-1] != 's' else ''}"
                )
                break

        return common_property if common_property != "Unknown" else f"Unknown {property_name}"

    @pyqtSlot()
    def translate_plot_titles(self, fmt: str = "") -> None:
        """Translate a given string format for plot titles based on file metadata.

        If there are no active plots, the name of the plot title will be displayed, otherwise
        the title format will be translated and used.

        Called by either modifying the plot title format or the title text size.

        Args:
            * fmt (str, optional): The plot title format that will be translated.
        """
        title_format: str
        title_tags: dict[str, str] = {}

        if len(self.plotted_file_properties()) == 0:
            title_format = "[PlotType]"
        else:
            title_format = fmt or self.line_main_title.text()
            title_tags = {
                "[Application]": self.common_properties("Application"),
                "[Resolution]": self.common_properties("Resolution"),
                "[Runtime]": self.common_properties("Runtime"),
                "[GPU]": self.common_properties("GPU"),
                "[PlotType]": "",
                "[DataSource]": session("PrimaryDataSource"),
                # TODO: Modify to support additional axes
            }
            scatter_data_sources: str = (
                f"{session('PrimaryDataSource')} / {session('SecondaryDataSource')}"
            )

        translated_title: str
        title_font_size: int = self.spin_main_title_size.value()
        opening_tag: str = f"<span style='font-size:{title_font_size}pt;'>"

        for plot, widget in self.plots.items():
            translated_title = title_format
            title_tags["[PlotType]"] = plot

            for key, value in title_tags.items():
                if key == "[DataSource]":
                    if plot == "Scatter":
                        value = scatter_data_sources
                    elif plot == "Experience":
                        value = "FPS/Latency"
                elif key == "[PlotType]" and plot == "Experience":
                    value = "Gameplay Experience"
                translated_title = translated_title.replace(key, value)

            widget.setTitle(f"{opening_tag}{translated_title}</span>")

    def plot_axis_style(self) -> dict[str, str]:
        """Return a consistent stylization for plot axis labels based on the current stylesheet."""
        font_size: int = self.spin_axis_label_size.value()
        return {
            "color": f"#{'c0c0c0' if session('DarkMode') else '000'}",
            "font-size": f"{font_size}pt",
        }

    def update_line_plot_scale(self, style: dict[str, str] = None) -> None:
        """Modify the line plot scale and axis labels in response to the selected time scale.

        Args:
            * style (dict[str, str], optional): CSS rules for styling the line edit widget.
        """
        style = style or self.plot_axis_style()
        self.plots["Line"].getAxis("bottom").setScale(1 / time_scale())
        self.plots["Line"].getAxis("bottom").setLabel(f"Elapsed Time {time_str_long()}", **style)
        self.plots["Line"].getAxis("left").setLabel(session("PrimaryDataSource"), **style)

    def update_gridlines(self) -> None:
        """Show, hide, or modify the opacity of gridlines on the plots."""
        for plot in self.plots.values():
            plot.showGrid(
                x=self.check_gridlines_vertical.isChecked(),
                y=self.check_gridlines_horizontal.isChecked(),
                alpha=self.spin_gridline_opacity.value() / 100,
            )

    @stopwatch(silent=True)
    @pyqtSlot()
    def translate_axis_labels(self) -> None:
        """Update axis labels and size based on current selections."""
        style = self.plot_axis_style()
        primary_source: str = session("PrimaryDataSource")
        secondary_source: str = session("SecondaryDataSource") or primary_source
        font: QFont = QFontDatabase.font("Open Sans", "Regular", 0)
        font.setPixelSize(int(setting("Plotting", "AxisLabelFontSize")) + 3)

        x_axis_label: dict[str, str] = {
            # Line plot labels are handled via `update_line_plot_scale()`
            "Percentiles": "Percentile (k)",
            "Histogram": primary_source,
            "Box": primary_source,
            "Scatter": secondary_source,
            "Experience": "System Latency (ms) / Frame Rate (fps)",
        }

        y_axis_label: dict[str, str] = {
            # Line plot labels are handled via `update_line_plot_scale()`
            "Percentiles": primary_source,
            "Histogram": "Frequency (%)",
            "Box": None,
            "Scatter": primary_source,
            "Experience": None,
        }

        for name, plot in self.plots.items():
            plot.getAxis("bottom").setStyle(tickFont=font)
            plot.getAxis("left").setStyle(tickFont=font)

            if name == "Line":
                self.update_line_plot_scale(style)
                continue

            plot.getAxis("bottom").setLabel(x_axis_label[name], **style)
            plot.getAxis("left").setLabel(y_axis_label[name], **style)

            # Histogram plot shows relative distribution, so the scale will always be 100x.
            plot.getAxis("left").setScale(100 if name == "Histogram" else 1)

    def set_plot_color_scheme(self) -> None:
        """Apply a light or dark color scheme to all pyqtgraph plots."""
        dark_mode: bool = session("DarkMode")

        bg_color: tuple = (32, 32, 32) if dark_mode else (255, 255, 255)
        axis_color: tuple = (192, 192, 192) if dark_mode else (0, 0, 0)

        for plot in self.plots.values():
            plot.setBackground(background=bg_color)

            get_axis = plot.getAxis
            for axis in ("bottom", "left"):
                ax = get_axis(axis)
                ax.setPen(axis_color)
                ax.setTextPen(axis_color)

    @pyqtSlot(bool)
    def apply_stylesheet(self, dark_mode: bool = False) -> None:
        """Change the current style sheet to light/dark mode."""
        set_value("General", "UseDarkStylesheet", dark_mode)
        set_session_value("DarkMode", dark_mode)
        self.setStyleSheet(current_stylesheet())

        self.set_plot_color_scheme()
        SquareLegendItem.style_backgrounds()

        # Reapply warning styles to prevent inappropriate colorations
        self.warn_of_custom_values()
        self.warn_of_negative_values()
        self.warn_of_expression_error()

    def prompt_for_config_reset(self) -> None:
        """Prompt user with a yes/no dialog box to restore the default configuration values."""
        user_response = QMessageBox.information(
            self,
            "Confirmation",
            "Restore all default configuration values?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if user_response == QMessageBox.StandardButton.Yes:
            self.reset_config_settings()

    @pyqtSlot(int)
    def show_data_source_groups(self, tab_index: int) -> None:
        """Adjust the visibility of certain elements when the user changes to another tab.

        This functionality is intended to be used more impactfully once pyqtgraph has merged an
        ongoing PR for a MultiAxisPlotWidget, which will provide a simpler means of implementing
        the multiplotting feature.
        """
        self.btn_multiplot_settings.setVisible(False)  # Hide until MultiAxisPlotWidget is accepted
        self.controls_scatter_data.setVisible(tab_index == Tab.Scatter.value)

    def reset_config_settings(self) -> None:
        """Reset the configuration file to default settings and update widgets accordingly."""
        StatusBarWithQueue.post("Preferences have been reset to default values.")
        logger.debug("Reset config settings to defaults")
        set_defaults(current_version_str())
        self.metrics_dialog.reset_to_defaults()
        self.load_user_config()
        self.update_percentile_steps()
        self.update_metric_visibility()

    def reset_legend_position(self) -> None:
        """Return the plot legends to their default position (top-right corner)."""
        for plot in self.plots.values():
            plot.viewbox.legend.reset_position()
        self.btn_reset_legend_position.setHidden(True)

    def update_gui_log(self, msg: str) -> None:
        """Copy each `logger.emit()` and redirect it to the debug log text field."""
        self.text_log.appendPlainText(msg)

    def batch_spawn_workers(self, file_list: list[Path]) -> None:
        """Spin up workers for each file that was passed in."""
        if (num_files := len(file_list)) == 0:
            logger.info("No files were passed to workers")
            return

        bar_max: int = self.progressbar_main.maximum()
        pending_files: int = bar_max if bar_max > 1 else 0
        self.progressbar_main.setMaximum(pending_files + num_files)

        self.setCursor(Qt.CursorShape.BusyCursor)
        set_session_value("BusyCursor", True)

        # Track how long it takes to load all of the selected files
        self.batch_count = num_files
        self.batch_size = sum(f.stat().st_size for f in file_list)
        self.batch_time = perf_counter_ns()

        for file in file_list:
            try:
                self.spawn_worker(file)
            except Exception as e:
                log_exception(logger, e, "Failed to create worker for target")

    def spawn_worker(self, file_path: Path) -> None:
        """Spin up a worker on a separate thread to read a file."""
        loaded: bool = str(file_path) in PlotObject.all_keys()
        if file_path.is_file() and not loaded:
            worker = Worker(self.create_plot_obj, file_path)
            worker.signals.error.connect(lambda x: log_exception(logger, x))
            worker.signals.result.connect(self.add_file_to_models)
            worker.signals.finished.connect(self.update_progress_bar)
            return self.pool.start(worker.work)

        if loaded:
            logger.info(f"'{file_path}' is already loaded")
        elif not file_path.is_file():
            logger.error(f"Invalid path received for {file_path}")
        self.update_progress_bar()

    def report_batch_processing_time(self) -> None:
        """When all files have been processed, log the time, total size, and approximate I/O rate."""
        self.batch_time = perf_counter_ns() - self.batch_time
        batch_rate: float = (self.batch_size / self.batch_time) * 1000
        logger.debug(
            f"Processed {self.batch_count} files totaling {size_from_bytes(self.batch_size)} "
            f"in {time_from_ns(self.batch_time)} "
            f"({batch_rate:.1f} MB/s)"
        )
        self.batch_count = self.batch_size = self.batch_time = 0

    @pyqtSlot(bool)
    def update_progress_bar(self) -> None:
        """Increment the GUI progress bar or reset it one second after reaching the max value."""
        self.progressbar_main.setValue(self.progressbar_main.value() + 1)

        # Reset the progress bar after one second if all work has been completed or if the active
        # I/O thread count is zero (to prevent stalled progress from failed file reads)
        maximum_reached: bool = self.progressbar_main.value() >= self.progressbar_main.maximum()
        no_active_threads: bool = self.pool.activeThreadCount() == 0

        if maximum_reached or no_active_threads:
            if self.batch_time != 0:
                self.report_batch_processing_time()

            QTimer.singleShot(1000, self.reset_progress_bar)

    def reset_progress_bar(self) -> None:
        """Reset the progress bar values."""
        self.progressbar_main.setValue(0)
        self.progressbar_main.setMaximum(1)

        self.setCursor(Qt.CursorShape.ArrowCursor)
        set_session_value("BusyCursor", False)

    def launch_file_explorer(self, launch_path: str = "") -> tuple[list[str], str]:
        """Open a native dialog window for selecting files.

        Args:
            * use_path (str, optional): Path to open the dialog window at. Defaults to app root.

        Returns:
            * Tuple containing the file names and extension used if selecting files. Selecting
            folders returns the absolute path of the target folder.
        """
        # Use the provided path, if it exists. Otherwise use the app root.
        if not launch_path or not Path(launch_path).exists():
            launch_path = self.base_path

        return self.file_dialog.getOpenFileNames(
            self,
            "Select File(s)",
            launch_path,
            "Common formats (*.csv; *.hml; *.txt);;All Files (*.*)",
        )

    def launch_folder_explorer(self, launch_path: str = "") -> str:
        """Open a native dialog window for selecting a folder.

        Args:
            * use_path (str, optional): Path to open the dialog window at. Defaults to app root.

        Returns:
            * Absolute path of the folder to be processed.
        """
        # Use the provided path, if it exists. Otherwise use the app root.
        if not launch_path or not Path(launch_path).exists():
            launch_path = self.base_path

        return self.file_dialog.getExistingDirectory(
            self,
            "Select a Folder",
            launch_path,
        )

    @pyqtSlot(bool)
    def add_files(self) -> None:
        """Pop up a native file dialog for choosing file(s) to import.

        Todo:
            * Improve logging output during concurrent processing.
        """
        last_used_path: str = setting("General", "LastUsedPath")
        file_list, ext_group = self.launch_file_explorer(last_used_path)

        # User canceled the operation
        if not file_list:
            return

        num_files = len(file_list)
        StatusBarWithQueue.post(f"Importing {num_files} file{'s' if num_files > 1 else ''}...")
        logger.debug(f"Importing {num_files} files using extension filter: '{ext_group}'")
        set_value("General", "LastUsedPath", Path(file_list[0]).parent)
        self.batch_spawn_workers([Path(file) for file in file_list])

    @pyqtSlot(bool)
    def add_folder(self) -> None:
        """Pop up a native file dialog for choosing a folder to import."""
        last_used_path = setting("General", "LastUsedPath")
        folder_path = self.launch_folder_explorer(last_used_path)

        # User canceled the operation
        if not folder_path:
            return

        set_value("General", "LastUsedPath", folder_path)
        all_files: list = self.walk_through_directory([folder_path])
        num_files: int = len(all_files)

        if num_files > 0:
            StatusBarWithQueue.post(f"Importing {num_files} file{'s' if num_files > 1 else ''}...")

        self.batch_spawn_workers(all_files)

    def change_export_path(self) -> None:
        """Open a folder dialog window for the user to select the new output path."""
        folder_path = self.launch_folder_explorer(self.base_path)
        self.line_exporting_path.setText(folder_path)

    def change_logging_path(self) -> None:
        """Open a folder dialog window for the user to select the new logging path."""
        folder_path = self.launch_folder_explorer(self.base_path)
        self.line_logging_path.setText(folder_path)

    def create_plot_obj(self, file_path: Path) -> PlotObject:
        """Worker task for creating a PlotObject on a non-GUI thread."""
        return PlotObject(file_path, self.integrity_update_event)

    def update_file_icon(self, file_path: Path, file_integrity: Integrity) -> None:
        """Update the integrity icon next to each loaded file in `list_loaded_files`."""
        self.list_loaded_files.update_icon(
            file_path,
            file_integrity,
            self.integrity_icon.get(file_integrity.name, file_integrity.Invalid.name),
        )

    @pyqtSlot(tuple)
    def integrity_update_event(self, path_and_integrity: tuple) -> None:
        """Signal the list_loaded_files QListWidget to update the icon for a given file.

        This is called for any `__setattr__()` call that touches the integrity attribute of a
        CaptureFile object, which are encapsulated in PlotObjects.
        """
        try:
            file_path, file_integrity = path_and_integrity
            new_item: bool = self.list_loaded_files.item_by_path(file_path) is None

            if new_item:
                new_row = FlexibleListItem(file_path)
                new_row.setIcon(
                    self.integrity_icon.get(file_integrity.name, file_integrity.Invalid.name)
                )
                new_row.setToolTip(file_integrity.description())
                new_row.setFlags(Qt.ItemFlag.NoItemFlags)
                self.list_loaded_files.addItem(new_row)
            else:
                self.update_file_icon(file_path, file_integrity)
        except Exception as e:
            log_exception(logger, e, "Integrity update callback failed")

    @pyqtSlot(PlotObject)
    def add_file_to_models(self, plot_obj: PlotObject) -> None:
        """Invoke a file's first integrity update and add its path to the browser model."""
        try:
            file_path: Path = plot_obj.file.path
            file_integrity: Integrity = plot_obj.file.integrity
            self.update_file_icon(file_path, file_integrity)
            self.update_combo_models()
        except Exception:
            # No CaptureFile object was created
            StatusBarWithQueue.post("There was a problem reading a file. See the log for details.")

    def filter_loaded_files(self, include: bool = True, field: str = "", term: str = "") -> None:
        """Filter the loaded files list by a given field and term."""
        previous_selection = self.list_loaded_files.selectedItems()

        if term:
            self.file_filter[include][field] = term.lower()
        else:
            self.file_filter[include].pop(field, None)

        self.list_loaded_files.update_label_filter(self.file_filter)

        changed_selection: bool = previous_selection != self.list_loaded_files.selectedItems()
        if changed_selection and self.list_loaded_files.count() > 0:
            self.refresh_plots()

    @pyqtSlot(bool)
    def remove_all_files(self) -> None:
        """Remove all loaded files from the application and reset plots to their initial state."""
        if (num_files := self.list_loaded_files.count()) > 0:
            self.clear_plots()
            self.reset_data_models()

            PlotObject.remove_all_objects()

            self.update_combo_models()
            self.translate_plot_titles()

            logger.debug(f"{num_files} file{'s were' if num_files > 1 else ' was'} removed")

    @pyqtSlot()
    def clear_selected_plot(self) -> None:
        """Remove just the selected file from the plots."""
        if (selected := PlotObject.get_selected()) is None:
            return

        selected_row = self.list_loaded_files.item_by_path(selected.file.path)
        selected_row.setSelected(False)

        self.list_loaded_files.emphasize_selected_file()
        self.plot_selected_files()

    @pyqtSlot(bool)
    def clear_plots(self, deselect: bool = True, drop_tables: bool = True) -> None:
        """Reset plot widgets to their initial states."""
        PlotObject.clear_plots(deselect)
        SquareLegendItem.clear_all()

        if deselect:
            self.list_loaded_files.clearSelection()
            self.list_loaded_files.emphasize_selected_file()

        self.reset_plot_views(clear=True)
        self.translate_plot_titles()

        # Reset named axis labels
        self.plots["Box"].getAxis("left").setTicks(None)

        if drop_tables:
            self.combo_stats_compare_against.setCurrentText("None")
            self.table_stats.reset_view()

    def reset_plot_views(self, clear: bool = False) -> None:
        """Reset or apply auto-ranging to the views of all plot widgets.

        Args:
            * clear (bool, optional): Determines if the plot widgets should remove all present
            items or simply readjust the viewbox range.
        """
        for plot in self.plots.values():
            if clear:
                plot.clear()
                plot.setRange(xRange=[0, 1], yRange=[0, 1], disableAutoRange=False)
                self.pyqtgraph_line.redraw_crosshair()
            else:
                plot.autoRange()

        for plot_name, pairs in self.plot_range_controls.items():
            for axis, widgets in pairs.items():
                self.clamp_range(plot_name, axis, widgets)

    def prescribe_plot_ranges(self) -> None:
        """Force a plot's axis range to start at zero if the clamp checkbox is ticked."""
        for plot_name, pairs in self.plot_range_controls.items():
            for widgets in pairs.values():
                _, _, clamp_widget, _ = widgets
                if clamp_widget is not None and clamp_widget.isChecked():
                    self.change_range(plot_name)

        if session("CurrentTabIndex") == Tab.Experience.value:
            self.pyqtgraph_experience.force_autorange()

    def clamp_range(self, plot_name, axis, widgets) -> None:
        """Clamp or release a plot's range values based on checkbox state."""
        axis_num = 0 if axis == "x" else 1
        min_widget, max_widget, clamp_widget, _ = widgets
        target_min, target_max = self.plots[plot_name].viewbox.state["targetRange"][axis_num]
        min_widget.setValue(
            0.0 if clamp_widget is not None and clamp_widget.isChecked() else target_min
        )
        max_widget.setValue(target_max)

    def clamp_axis(self, plot_name: str, axis: str) -> None:
        """Clamp or release a plot's axis based on checkbox state."""
        min_widget, _, clamp_widget, _ = self.plot_range_controls[plot_name][axis]
        if clamp_widget.isChecked():
            min_widget.setValue(0.0)

    @pyqtSlot()
    def change_range(self, plot_name: str) -> None:
        """Adjust the XY ranges for a given plot."""
        for axis, pairs in self.plot_range_controls[plot_name].items():
            min_widget, max_widget, _, _ = pairs
            range_min, range_max = min_widget.value(), max_widget.value()
            plot = self.plots[plot_name]
            set_range = plot.setXRange if axis == "x" else plot.setYRange
            set_range(min=range_min, max=range_max, padding=0)

    @pyqtSlot()
    def update_plot_ranges(self, plot_name: str) -> None:
        """Update the spinner widgets associated with a plot's current XY range."""
        min_x, min_y, max_x, max_y = self.plots[plot_name].viewRect().getCoords()

        for axis, widgets in self.plot_range_controls[plot_name].items():
            min_widget, max_widget, clamp_widget, _ = widgets
            clamp_setting = "ClampXMinimum" if axis == "x" else "ClampYMinimum"

            if clamp_widget is None or setting(plot_name, clamp_setting) != "True":
                min_widget.setValue(min_x if axis == "x" else min_y)
            max_widget.setValue(max_x if axis == "x" else max_y)

    @stopwatch(silent=True)
    def add_unplotted_files(self, unplotted_files: list) -> None:
        """Add selected but unplotted files to plots."""
        if not unplotted_files or session("SwappingSources"):
            return

        viewing_stutter: bool = session("PrimaryDataSource") == "Stutter (%)"
        self.progressbar_main.setMaximum(len(unplotted_files))

        for plot_obj in unplotted_files:
            try:
                plot_obj.plotted = True

                # Experience plot uses fixed data sources
                self.add_plot("Experience", plot_obj.curves["Experience"])

                if not plot_obj.plottable_source:
                    continue

                self.add_plot("Line", plot_obj.curves["Line"])

                # Skip other plots if stutter is the current data source
                if viewing_stutter:
                    continue

                self.add_plot("Percentiles", plot_obj.curves["Percentiles"])
                self.add_plot("Histogram", plot_obj.curves["Histogram"])

                # Box plot includes boxes, error bars, and scatter plots
                self.add_plot("Box", plot_obj.curves["Box"])
                self.add_plot("Box", plot_obj.curves["Error"])
                if session("ShowOutliers"):
                    self.add_plot("Box", plot_obj.curves["Outliers"])

                if plot_obj.plottable_scatter:
                    self.add_plot("Scatter", plot_obj.curves["Scatter"])
            except Exception as e:
                plot_obj.plotted = False
                logger.error(f"{plot_obj.file.name} not plotted")
                log_exception(logger, e, "Failed to plot file")
            finally:
                self.update_progress_bar()
        self.warn_of_negative_values()

    @stopwatch(silent=True)
    def warn_of_negative_values(self) -> None:
        """Show or hide caution labels when a plot contains negative data on a clamped axis."""
        for plot_name in self.plots.keys():
            # Experience plot uses a different axis format than other plots
            for axis, widgets in self.plot_range_controls[plot_name].items():
                _, _, clamp_widget, label = widgets

                if None in {clamp_widget, label}:
                    continue

                negative_value: bool = False
                if clamp_widget.isChecked():
                    try:
                        negative_value = (
                            sum(
                                min(curve.xData if axis == "x" else curve.yData) < 0
                                for curve in self.plots[plot_name].items()
                                if isinstance(
                                    curve,
                                    (PlotDataItem, UnclickableBarGraphItem),
                                )
                            )
                            > 0
                        )
                    except TypeError:
                        break
                    except Exception as e:
                        logger.error(f"Non-numeric data in {axis} axis of {plot_name} plot")
                        log_exception(logger, e)
                label.setVisible(negative_value)

    @stopwatch(silent=True)
    def warn_of_custom_values(self) -> None:
        """Apply a tinted background to certain widgets if their values differ from the defaults."""
        dark_mode: bool = session("DarkMode")
        background: str = "#382626" if dark_mode else "#fff0f0"
        font: str = "#fbeaea" if dark_mode else "#af2121"

        for phrase, associations in self.functional_widgets.items():
            widget, widget_type, section = associations
            widget.setStyleSheet(
                ""
                if default_value(section, phrase)
                else f"{widget_type} {{background-color:{background}; color:{font};}}"
            )

    def remove_deselected_plots(self, deselected_files: list) -> None:
        """Remove any deselected files from plots."""
        for plot_obj in deselected_files:
            for name, widget in self.plots.items():
                if (curve := plot_obj.curves[name]) is None:
                    continue
                elif name == "Box":
                    for curve in self.get_box_curves(plot_obj):
                        widget.removeItem(curve)
                else:
                    widget.removeItem(curve)
                    curve.sigClicked.disconnect()  # Disconnect from all slots
            plot_obj.plotted = False

    @pyqtSlot()
    def update_stutter_parameters(self) -> None:
        """Force recalculation of stutter metrics, then update plots/tables."""
        self.warn_of_custom_values()
        self.recalculate_stutter_stats()

        # Only update plots if viewing the stutter data source
        if "Stutter (%)" in {session("PrimaryDataSource"), session("SecondaryDataSource")}:
            self.refresh_plots()

    @pyqtSlot(bool)
    def recalculate_stutter_stats(self, plot_obj: PlotObject = None) -> None:
        """Force recalculation of stutter metrics for a specific file or all files.

        Args:
            * plot_obj (PlotObject, optional): The PlotObject instance that specifically needs its
            statistics to be recalculated. If not provided, statistics will be recalculated for all
            currently plotted files.
        """
        if plot_obj is None:
            PlotObject.update_all_stutter_metrics()
        else:
            PlotObject.update_stutter_metrics(plot_obj)
        self.refresh_stats()

    @pyqtSlot()
    def recalculate_time_stats(self, plot_obj: PlotObject = None) -> None:
        """Force recalculation of time-related metrics for a specific file or all files.

        Args:
            * plot_obj (PlotObject, optional): The PlotObject instance that specifically needs its
            statistics to be recalculated. If not provided, statistics will be recalculated for all
            currently plotted files.
        """
        if plot_obj is None:
            PlotObject.update_all_time_metrics()
        else:
            PlotObject.update_time_metrics(plot_obj)
        self.refresh_stats()

    @stopwatch(silent=True)
    @pyqtSlot()
    def refresh_stats(self) -> None:
        """Refresh the file stats table to account for a new file, modified order, or altered file."""
        selected_files = sorted(
            self.list_loaded_files.get_selected_items(), key=PlotObject.legend_order.index
        )
        self.table_stats.reset_view()

        for plot_obj in selected_files:
            plot_obj.calculate_stats()
            self.add_file_stats(plot_obj.get_all_stats())

        self.table_stats.resizeColumnsToContents()

    @pyqtSlot()
    def update_dragged_line_plot(self) -> None:
        """Refresh a specific file while its line curve is being dragged.

        Args:
            * plot_obj (PlotObject, optional): PlotObject instance of the curve being altered. If not
            provided, the currently selected PlotObject is used.
        """
        PlotObject.get_selected().define_curves("Line")

    @staticmethod
    def get_box_curves(plot_obj: PlotObject) -> Generator:
        """Return a generator for a PlotObject's valid box-related curves.

        Args:
            * plot_obj (PlotObject): The file whose curves will be returned.

        Returns:
            * Generator: A filtered collection of valid box, error, and outlier curves.
        """
        return (
            curve
            for plot, curve in plot_obj.curves.items()
            if plot in {"Box", "Error", "Outliers"}
            and plot_obj.plottable_source
            and curve is not None
        )

    def order_box_plots(self, axis_only: bool = False) -> None:
        """Overwrite x axis values for each box plot and replace axis labels with legend names."""
        plotted_files: list[PlotObject] = [
            plot_obj
            for plot_obj in PlotObject.legend_order[::-1]
            if plot_obj.plotted
            and hasattr(plot_obj, "plottable_source")  # Workaround for LDAT files
            and plot_obj.plottable_source
        ]

        if not plotted_files:
            return

        height: int = int(setting("Box", "Height"))
        spacing: int = int(setting("Box", "Spacing"))
        intervals: range = range(spacing, (1 + len(plotted_files)) * spacing, spacing)
        legend_names: list = [file.legend_name for file in plotted_files]
        legends_as_ticks: list = [list(zip(intervals, legend_names))]
        self.plots["Box"].getAxis("left").setTicks(legends_as_ticks)

        if axis_only:
            return

        for index, plot_obj in enumerate(plotted_files):
            for plot in {"Box", "Error", "Outliers"}:
                if (curve := plot_obj.curves[plot]) is not None:
                    if hasattr(curve, "height") and curve.opts["height"][0] != height:
                        if isinstance(curve, UnclickableBarGraphItem):
                            curve.setOpts(height=[height])
                        elif isinstance(curve, ClickableErrorBarItem):
                            curve.setOpts(height=repeat(height, 5))
                    curve.setY((1 + index) * spacing)

    def style_callout_labels(self, value, units: str = "", selected: bool = False) -> str:
        """Provide HTML styling to value callout labels for the experience plot."""
        font_size: int = int(setting("Experience", "CalloutTextSize"))
        precision: int = int(setting("General", "DecimalPlaces"))
        label_color: tuple = (192, 192, 192) if session("DarkMode") else (0, 0, 0)
        label_color = label_color + (
            (int(setting("Plotting", "NormalAlpha")),)
            if session("SelectedFilePath") == ""
            else (int(setting("Plotting", "EmphasizedAlpha")),)
            if selected
            else (int(setting("Plotting", "DiminishedAlpha")),)
        )

        if isinstance(value, float):
            value = f"{value:.{precision}f}"

        span_tags: str = (
            f"<span style='font-size:{font_size}pt;" f"font-weight:bold;color:rgba{label_color};'>"
        )
        return f"{span_tags}{value}{f' {units}' if units else ''}</span>"

    @stopwatch(silent=True)
    @pyqtSlot()
    def order_experience_plots(self) -> None:
        """Draw value callouts for the three points of interest for each experience curve."""
        experience_plot = self.plots["Experience"]
        height: int = int(setting("Experience", "Height"))
        spacing: int = int(setting("Experience", "Spacing"))
        frameview_files: list[PlotObject] = [
            plot_obj
            for plot_obj in PlotObject.legend_order[::-1]
            if plot_obj.plotted
            and plot_obj.file.app_name == "FrameView"
            and plot_obj.file.alias_present("System Latency")
        ]

        # Clear previous text labels
        existing_labels: Generator = (
            label for label in experience_plot.items() if isinstance(label, TextItem)
        )
        for label_object in existing_labels:
            experience_plot.removeItem(label_object)

        curve: Any = None
        selected: bool = False
        source_size: int = max(int(setting("Experience", "CalloutTextSize")) - 2, 6)
        position: int = 0

        label_text: str = ""
        label_object: TextItem
        label_value: float = 0.0
        latency = low_fps = avg_fps = 0.0

        for index, plot_obj in enumerate(frameview_files):
            if curve := plot_obj.curves["Experience"]:
                # Keep bar heights up to date
                if curve.opts["height"] != height:
                    curve.setOpts(height=height)

                selected = plot_obj.file.path == session("SelectedFilePath")
                using_fallback: bool = "System Latency" in plot_obj.file.fallbacks_in_use
                position = (1 + index) * spacing
                curve.setY(position)

                latency, low_fps, avg_fps = (
                    curve.opts["x0"][0],  # Negative axis value for latency
                    curve.opts["x1"][0],
                    curve.opts["x1"][1],
                )

                # Latency label
                label_value = latency
                label_text = self.style_callout_labels(-label_value, "ms", selected)
                label_object = TextItem(html=label_text, anchor=(1.0, 0.5))
                experience_plot.addItem(label_object)
                label_object.setPos(label_value, position)

                # Legend name and latency header (with fallback marker)
                label_text = self.style_callout_labels(
                    f"{plot_obj.legend_name}<br>"
                    f"<span style='font-weight:normal;font-size:{source_size}pt;'>"
                    f"{'Fallback: ' if using_fallback else ''}"
                    f"{plot_obj.file.header_by_alias('System Latency')}</span>",
                    "",
                    selected,
                )
                label_object = TextItem(html=label_text, anchor=(-0.05, 0.5))
                experience_plot.addItem(label_object)
                label_object.setPos(label_value, position)  # Use latency position

                # 1st fps percentile label
                label_value = low_fps
                label_text = self.style_callout_labels(label_value, "fps", selected)
                label_object = TextItem(html=label_text, anchor=(1.0, 0.5))
                experience_plot.addItem(label_object)
                label_object.setPos(label_value, position)

                # Mean fps label
                label_value = avg_fps
                label_text = self.style_callout_labels(label_value, "fps", selected)
                label_object = TextItem(html=label_text, anchor=(-0.05, 0.5))
                experience_plot.addItem(label_object)
                label_object.setPos(label_value, position)

    @pyqtSlot()
    def update_dropped_line_plot(self) -> None:
        """Refresh the dropped file's offset and recalculate file statistics."""
        selected_plot = PlotObject.get_selected()
        selected_plot.file.trim_time_axis(relation="Drop")

        for plot_name, curve in selected_plot.curves.items():
            if curve is None:
                continue

            selected_plot.define_curves(plot_name)

        PlotObject.update_stutter_metrics(selected_plot)
        self.refresh_stats()
        self.order_box_plots()
        self.order_experience_plots()

    @pyqtSlot(int)
    def modify_selected_plot(self) -> None:
        """Refresh the trimmed file's time series and recalculate file statistics."""
        if (target := PlotObject.get_selected()) is not None:
            self.recalculate_stutter_stats(target)
            self.update_file_icon(target.file.path, target.file.integrity)  # Update tooltips
        self.refresh_plots()

    @pyqtSlot(int)
    def modify_all_plots(self) -> None:
        """Refresh the trimmed file's time series and recalculate file statistics."""
        self.recalculate_stutter_stats()
        self.refresh_plots()

    @pyqtSlot()
    @stopwatch(silent=True)
    def refresh_plots(self) -> None:
        """Refresh currently plotted items, usually in response to parameter changes."""
        self.clear_plots(deselect=False, drop_tables=False)
        self.plot_selected_files()
        self.list_loaded_files.emphasize_selected_file()
        SquareLegendItem.update_all()

    @pyqtSlot(str)
    def update_primary_source(self, current_text: str = "") -> None:
        """Return a data series corresponding to the x axis selection."""
        # Don't update if the source text has not changed
        if current_text in {"", session("PrimaryDataSource")}:
            return

        viewing_stutter: bool = current_text == "Stutter (%)"
        set_session_value("PrimaryDataSource", current_text)

        self.translate_axis_labels()
        self.refresh_plots()

        related_widgets = {
            # Line plots can show stutter without issue
            "Percentiles": (self.caution_label_stutter_percentiles, self.controls_percentiles),
            "Histogram": (self.caution_label_stutter_histogram, self.controls_histogram),
            "Box": (self.caution_label_stutter_box, self.controls_box),
            # Scatter plot widgets are handled from `update_scatter_visibility()`
            # Experience plots use static data sources
        }

        for plot_name, widgets in related_widgets.items():
            self.plots[plot_name].setHidden(viewing_stutter)
            label, container = widgets
            label.setVisible(viewing_stutter)
            container.setHidden(viewing_stutter)

        self.update_scatter_visibility()

    @pyqtSlot(str)
    def update_secondary_source(self, current_text: str = "") -> None:
        """Return a data series corresponding to the y axis selection. Only applies to Scatter plot."""
        if (
            current_text in {"", session("SecondaryDataSource")}
            or session("EnableScatterPlots") == "False"
        ):
            return

        set_session_value("SecondaryDataSource", current_text)
        if self.update_scatter_visibility():
            self.translate_axis_labels()
            self.refresh_plots()

    @stopwatch(silent=True)
    def update_scatter_visibility(self) -> bool:
        """Control the visibility of scatter plot widgets depending on current settings."""
        scatter_toggled = session("EnableScatterPlots")
        stutter_in_primary: bool = session("PrimaryDataSource") == "Stutter (%)"
        stutter_in_secondary: bool = session("SecondaryDataSource") == "Stutter (%)"
        not_viewing_stutter: bool = not (stutter_in_primary or stutter_in_secondary)
        show_scatter_plot: bool = scatter_toggled and not_viewing_stutter

        self.controls_scatter_toggle.setHidden(scatter_toggled)
        self.plots["Scatter"].setVisible(show_scatter_plot)
        self.controls_scatter.setVisible(show_scatter_plot)
        self.caution_label_stutter_scatter.setHidden(
            not_viewing_stutter if scatter_toggled else True
        )
        return show_scatter_plot

    @stopwatch(silent=True)
    @pyqtSlot(bool)
    def toggle_outliers(self, toggled: bool = False) -> None:
        """Toggle the display of outlier points on the box plot."""
        set_session_value("ShowOutliers", toggled)
        self.refresh_plots()

    @stopwatch(silent=True)
    @pyqtSlot(bool)
    def toggle_scatter_plot(self, toggled: bool = False) -> None:
        """Update local and class variables related to plotting scatter data."""
        set_session_value("EnableScatterPlots", toggled)
        set_session_value("SecondaryDataSource", self.combo_secondary_source.currentText())
        self.update_scatter_visibility()

        if toggled:
            self.refresh_plots()

    @pyqtSlot()
    def swap_data_sources(self) -> None:
        """Reverse the current primary and secondary data sources."""
        if session("PrimaryDataSource") == session("SecondaryDataSource"):
            return

        primary_index: int = self.combo_primary_source.currentIndex()
        secondary_index: int = self.combo_secondary_source.currentIndex()

        set_session_value("SwappingSources", True)
        self.combo_primary_source.setCurrentIndex(secondary_index)
        set_session_value("SwappingSources", False)
        self.combo_secondary_source.setCurrentIndex(primary_index)

    @stopwatch(silent=True)
    @pyqtSlot()
    def plot_selected_files(self) -> None:
        """Update each plot according to items selected on self.list_loaded_files.

        Avoids plotting any data set that is already plotted or is unable to be plotted. Also
        removes any plots that are no longer plotted.
        """
        selected_files: set[str] = set(self.list_loaded_files.get_selected_items())
        already_plotted: set[str] = set(PlotObject.plotted_values())
        deselected_files: set[str] = already_plotted - selected_files
        unplotted_files: list[str] = list(selected_files - already_plotted)

        # Exit early if there's nothing new to plot
        if selected_files == already_plotted and not deselected_files and not unplotted_files:
            return

        # Restore plot colors if the selected curve is no longer plotted
        if session("SelectedFilePath") not in selected_files:
            PlotObject.reset_selection()
            self.list_loaded_files.emphasize_selected_file()

        if deselected_files and not selected_files:
            return self.clear_plots()

        self.remove_deselected_plots(deselected_files)
        self.add_unplotted_files(unplotted_files)
        self.order_legend_items()

        # Update stats table
        self.refresh_stats()

        # Update bar plots
        self.order_box_plots()
        self.order_experience_plots()

        # Update plot views after all items have been added
        self.translate_plot_titles()
        self.reset_plot_views()
        self.prescribe_plot_ranges()

    def plot_all_files(self) -> None:
        """Select all items in the file list and run `plot_selected_files()`."""
        self.list_loaded_files.selectAll()
        self.plot_selected_files()

    @stopwatch(silent=True)
    def order_legend_items(self) -> None:
        """Reorder the legends of all plots to match the order of the file list."""
        for plot in self.plots:
            self.plots[plot].viewbox.legend.reorder_legend_items()

    def reorder_legends(self) -> None:
        """Reorder plot legends and redraw bar-based plots."""
        self.order_legend_items()
        self.refresh_stats()
        self.order_box_plots()
        self.order_experience_plots()
        # self.refresh_plots()  # Causes flashing. Not necessary until curves use ordered z-values.

    def open_log_folder(self) -> None:
        """Open Windows Explorer at the logging location.

        Uses subprocess.run() to create the Explorer process without using a shell.
        """
        run([self.native_explorer_path, logging_path()], close_fds=True, shell=False)

    def open_output_folder(self) -> None:
        """Open Windows Explorer at the output location.

        Uses subprocess.run() to create the Explorer process without using a shell.
        """
        run([self.native_explorer_path, output_location()], close_fds=True, shell=False)

    @stopwatch(silent=True)
    def add_file_stats(self, stats: list) -> None:
        """Insert a file's statistics as a row in the table."""
        table: SharedEditTableView = self.table_stats
        model = table.model()
        item = CustomSortItem

        row: int = model.rowCount()
        precision: int = int(setting("General", "DecimalPlaces"))
        converted_items: list = [
            item(v if isinstance(v, str) else f"{v:,.{precision}f}") for v in stats
        ]

        model.appendRow(converted_items)
        model.setSortRole(Qt.ItemDataRole.DisplayRole)
        table.setModel(model)

        for i, values in enumerate(self.table_headers):
            model.item(row, i).setTextAlignment(values[0])

    def capture_stats_table(self) -> list[list[str]]:
        """Transcribe the immediate contents of the stats table into a list.

        Columns that are not displayed in the table will not be included.
        """
        model = self.table_stats.model()
        rows: range = range(model.rowCount())
        columns: range = range(model.columnCount())

        data: list[list[str]] = [
            [model.horizontalHeaderItem(col).text().replace("\n", " ") for col in columns]
        ]

        data.extend([model.item(row, col).text() for col in columns] for row in rows)

        return data

    def export_current_view(self) -> None:
        """Export the current tab's view, if supported."""
        tab_index: int = self.view_tabs.currentIndex()
        exportable_tabs: dict = {
            Tab.Line.value: self.plots["Line"].viewbox.export_image,
            Tab.Percentiles.value: self.plots["Percentiles"].viewbox.export_image,
            Tab.Histogram.value: self.plots["Histogram"].viewbox.export_image,
            Tab.Box.value: self.plots["Box"].viewbox.export_image,
            Tab.Scatter.value: self.plots["Scatter"].viewbox.export_image,
            Tab.Experience.value: self.plots["Experience"].viewbox.export_image,
            Tab.Statistics.value: self.export_stats,
            Tab.FileBrowser.value: self.export_browser_view,
        }
        if tab_index not in exportable_tabs:
            return
        return exportable_tabs[tab_index]()

    @pyqtSlot(bool)
    def export_stats(self) -> None:
        """Write a CSV from the data present in the file stats table."""
        # Don't create a file if the table is empty
        if self.table_stats.model().rowCount() == 0:
            StatusBarWithQueue.post("Statistics table is empty and will not be exported.")
            logger.debug("Did not write empty statistics file")
            return

        table_data: list[list[str]] = []
        base_file: str = self.combo_stats_compare_against.currentText()

        # Write base stats before relative stats to provide context
        if base_file != "None":
            self.compare_against_file("None")
            table_data = self.capture_stats_table()

            table_data.append([""])
            table_data.append([f"Compared against: {base_file}"])
            self.compare_against_file(base_file)

        table_data += self.capture_stats_table()
        write_stats_file(table_data)

    @pyqtSlot(bool)
    def export_browser_view(self) -> None:
        """Write a CSV from the data present in the file browser table."""
        model = self.table_file_browser.model()
        data = model._data
        rows: int = model.rowCount()
        columns: range = range(model.columnCount())

        # Don't create a file if the table is empty
        if self.combo_browse_file.currentText == "None" or rows == 0:
            StatusBarWithQueue.post("File browser table is empty and will not be exported.")
            logger.debug("Did not write empty file for file browser")
            return

        table_data: list[list[str]] = [[f"File path: {self.combo_browse_file.currentText()}"]]

        # Write the file name and filter expression (if one appears to have been used) at the top
        expression: str = self.line_browse_expression.text()
        if expression.strip() != "":
            table_data.append([f"Filter expression: {expression}"])

        # Include indices along with file headers and for each row
        row_with_index: list[str] = ["Index"]
        row_with_index += [
            model.headerData(col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
            for col in columns
        ]
        table_data.append(row_with_index)

        for row in range(rows):
            row_with_index = [int(data.index[row]) + 1]
            row_with_index += [str(data.iloc[row, col]) for col in columns]
            table_data.append(row_with_index)

        write_file_view(table_data)

    def choose_stats(self) -> None:
        """Open a dialog for the user to choose what statistics metrics to display."""
        user_saved_changes: bool = self.metrics_dialog.exec()
        if user_saved_changes:
            self.update_metric_visibility()
            self.refresh_stats()

    @pyqtSlot()
    @stopwatch(silent=True)
    def update_metric_visibility(self) -> None:
        """Update stat table headers and save header-widget pairs as encoded JSON."""
        self.header_visibility = self.metrics_dialog.current_selection()
        self.table_stats.update_header_visibility(self.header_visibility)

        # Store config setting as Base64-encoded JSON (dropping binary str prefix)
        json_obj: str = dumps(self.header_visibility)
        compressed_json: str = str(urlsafe_b64encode(json_obj.encode("utf-8")))
        set_value("Statistics", "Visibility", compressed_json[1:])

        if not running_from_exe():
            self.line_dev_encoded_visibility_json.setText(compressed_json)

    def update_dynamic_headers(self) -> None:
        """Change dynamic labels in the line plot scale, axis labels, and stat table headers."""
        PlotObject.update_headers()
        SignalingDelegate.update_table_headers()

        self.table_stats.set_header_labels()
        self.table_stats.resizeColumnsToContents()
        self.update_line_plot_scale()
        self.recalculate_time_stats()

    @stopwatch(silent=True)
    def reset_data_models(self) -> None:
        """Remove loaded files from GUI list and reset models used in the file browser tab."""
        self.list_loaded_files.clear()
        self.table_stats.reset_view()

        self.combo_stats_compare_against.setModel(DataFrameTableModel(["None"]))
        self.combo_browse_file.setModel(DataFrameTableModel(["None"]))
        self.combo_browse_header.setModel(DataFrameTableModel(["Show All"]))

    @stopwatch(silent=True)
    def update_combo_models(self) -> None:
        """Store file browser indexes to preserve selections between file imports."""
        # Save combo box states for the data sources and file browser
        primary_source: str = self.combo_primary_source.currentText()
        secondary_source: str = self.combo_secondary_source.currentText()
        compared_file: str = self.combo_stats_compare_against.currentText()
        file_browser_name: str = self.combo_browse_file.currentText()
        file_browser_header: str = self.combo_browse_header.currentText()

        # Update data models for data sources and file browser
        self.set_data_source_models()
        self.combo_browse_file.setModel(
            DataFrameTableModel(["None"] + sorted(PlotObject.all_keys()))
        )
        self.combo_stats_compare_against.setModel(
            DataFrameTableModel(["None"] + sorted(PlotObject.valid_keys()))
        )

        # Restore the combo box states for the data sources and file browser
        self.combo_primary_source.setCurrentText(primary_source)
        self.combo_secondary_source.setCurrentText(secondary_source)
        self.combo_stats_compare_against.setCurrentText(compared_file)
        self.combo_browse_file.setCurrentText(file_browser_name)
        self.combo_browse_header.setCurrentText(file_browser_header)

    def set_data_source_models(self) -> None:
        """Update the data source combo widgets with the default categories and individual headers."""
        default_sources: list[str] = list(default_data_sources())

        self.combo_primary_source.clear()
        self.combo_primary_source.addItems(default_sources + PlotObject.unique_data_sources)
        self.combo_primary_source.insertSeparator(len(default_sources))

        self.combo_secondary_source.clear()
        self.combo_secondary_source.addItems(default_sources + PlotObject.unique_data_sources)
        self.combo_secondary_source.insertSeparator(len(default_sources))

    @stopwatch(silent=True)
    def model_and_resize(self, file_data: DataFrame) -> None:
        """Perform rapid resizing of columns for the file browser.

        QTableView's resizeColumnsToContents() function considers the widths of every item and is
        consequently VERY slow when adjusting for data sets of even a few thousand rows. Here we
        set the table's data model to the file headers and last two rows of data, then resize that.
        Two rows were chosen so certain formats with irregular structures (e.g., HWiNFO logs) are
        handled as well. Although not fully accommodating, this method is extremely fast.
        """
        self.table_file_browser.setModel(DataFrameTableModel(file_data.iloc[-2:]))
        self.table_file_browser.resizeColumnsToContents()
        self.table_file_browser.setModel(DataFrameTableModel(file_data))
        self.line_browse_expression.setStyleSheet("")

    @pyqtSlot(str)
    def compare_against_file(self, base_file: str) -> None:
        """Change how file statistics are represented in the stats table."""
        SignalingDelegate.relative_stats = base_file != "None"
        PlotObject.compare_against_file = base_file
        self.refresh_stats()

    @stopwatch(silent=True)
    @pyqtSlot(str)
    def update_browser_files(self, file_path: str) -> None:
        """Update combo box with all loaded files (even invalid ones), then update file browser.

        With nothing selected or there's an error with creating a data mode, this sets an empty
        data model. Valid models are fed into a proxy model which supports filtering via column
        names and filter expressions; this also allows for sorting, but this is very slow.

        Todo:
            * Research speedup opportunities with QTreeView and custom lazy loader models.
        """
        if file_path == "None":
            self.table_file_browser.setModel(DataFrameTableModel())
            return

        try:
            self.model_and_resize(PlotObject.get_by_path(file_path).file.data)

            # Update text to match selection, invoked when a file is requested for viewing outside
            # of this tab view (i.e., via context menus)
            if self.combo_browse_file.currentText() != file_path:
                for idx in range(self.combo_browse_file.count()):
                    if self.combo_browse_file.itemText(idx) == file_path:
                        self.combo_browse_file.setCurrentIndex(idx)
        except Exception as e:
            log_exception(logger, e)

    @stopwatch(silent=True)
    @pyqtSlot(str)
    def update_browser_headers(self, file_path: str) -> None:
        """Update combo box with the browsed file's headers for column filtering."""
        filter_model = DataFrameTableModel(["Show All"])
        if file_path != "None":
            try:
                filter_model = DataFrameTableModel(
                    ["Show All"] + PlotObject.get_by_path(file_path).file.headers
                )
            except Exception as e:
                log_exception(logger, e)

        self.combo_browse_header.setModel(filter_model)

    # def manage_line_plot_axes(self) -> None:
    #     """
    #     TODO:
    #         * Retrieve changes when pressing OK
    #         * Verify if any changes were actually made
    #         * Commit changes to session variables
    #         * Refresh line plot if only axes or third/forth sources were changed
    #         * Only refresh line/scatter plot if second source changed
    #         * Refresh all plots if primary source changed
    #     """
    #     dialog = ManageLinePlotAxes(self.combo_primary_source.model())
    #     if not dialog.exec():
    #         return

    @pyqtSlot(str)
    def view_file_properties(self, target_file: str = "") -> None:
        """Raise the property dialog window, allowing for more idiomatic property management."""
        plot_obj = PlotObject.get_selected()
        if plot_obj is None:
            plot_obj = (
                PlotObject.get_by_path(target_file) or self.list_loaded_files.target_file.plot_obj
            )

        file = plot_obj.file
        initial_properties: dict[str, str] = file.properties
        initial_pen: tuple = plot_obj.pen

        # Raise dialog box containing file properties and accept changes
        dialog = FilePropertyDialog(plot_obj)
        running: bool = dialog.exec()

        # User canceled or closed window
        if not (running or dialog.changed_values):
            # Undo pen changes
            plot_obj.pen = initial_pen
            PlotObject.update_object_pen(plot_obj)
            return

        # Update pen color and width
        plot_obj.width = dialog.spin_pen_width.value()  # TODO: Store as metadata
        PlotObject.update_object_pen(plot_obj)

        # Check for new property data and update PlotObject accordingly
        updated_properties: dict = {
            "Application": dialog.line_property_application,
            "Resolution": dialog.line_property_resolution,
            "Runtime": dialog.line_property_runtime,
            "GPU": dialog.line_property_gpu,
            "Comments": dialog.line_property_comments,
            "Legend": (
                dialog.check_use_custom_legend.isChecked(),
                dialog.line_custom_legend.text(),
            ),
        }

        changed_value: bool = False
        new_value: str = ""
        for property, widget in updated_properties.items():
            previous_value: str = initial_properties[property]

            if property == "Legend":
                new_value = widget
            else:
                new_value = preserve_marks(previous_value, widget.text())

            if new_value != previous_value:
                file.properties[property] = new_value
                changed_value = True

        if changed_value:
            update_record(file.hash, file.properties)
            plot_obj.legend_name = dialog.line_custom_legend.text()
            self.update_legend_labels()

            # Preserve property updates in the session
            if not plot_obj.file.uses_saved_properties:
                plot_obj.file.uses_saved_properties = True

        # Update stats, legends, and plot titles
        plot_obj.set_capture_metrics()
        self.update_file_icon(file.path, file.integrity)  # Update tooltips
        self.translate_plot_titles()
        self.refresh_stats()
        self.order_box_plots()
        self.order_experience_plots()

    @pyqtSlot(str)
    def view_selected_file(self, target_file: str = "") -> None:
        """Load the selected file into the file browser, then change to that tab."""
        try:
            target_file = (
                target_file
                or self.list_loaded_files.target_file.path
                or PlotObject.get_selected().file.path
            )
            self.update_browser_files(target_file)

            # When viewing from the ContextMenuListWidget context menu, this tab may not be the
            # current view, so we switch for convenience
            if self.view_tabs.currentIndex() != Tab.FileBrowser.value:
                self.view_tabs.setCurrentIndex(Tab.FileBrowser.value)
        except Exception as e:
            log_exception(logger, e, f"Failed to browse selected file: {target_file}")

    @stopwatch(silent=True)
    def viewed_file(self) -> PlotObject:
        """Return PlotObject of the file currently viewed in the file browser."""
        return PlotObject.get_by_path(self.combo_browse_file.currentText())

    @stopwatch(silent=True)
    def browse_by_header(self, header: str) -> None:
        """Apply column-wise filtering to the current file model."""
        if (viewed := self.viewed_file()) is None:
            return

        try:
            if header != "Show All":
                self.model_and_resize(viewed.file.column(header))
            else:
                self.model_and_resize(viewed.file.data)
        except Exception as e:
            log_exception(logger, e)

    def warn_of_expression_error(self) -> None:
        """Apply conditional style to the filter expression widget when an evaluation fails."""
        if self.invalid_filter_expression:
            dark_mode: bool = session("DarkMode")
            background: str = "#382626" if dark_mode else "#fff0f0"
            font: str = "#fbeaea" if dark_mode else "#af2121"

            self.line_browse_expression.setStyleSheet(
                f"QLineEdit {{background-color:{background}; border-color:{font}; color:{font};}}"
            )

    @stopwatch(silent=True)
    @pyqtSlot(str)
    def browse_by_expression(self, expression: str = "") -> None:
        """Apply query filtering to the current file model.

        Verbatim files may have partial support from numeric coercion, depending on file structure.
        """
        self.invalid_filter_expression = False
        if (viewed := self.viewed_file()) is None:
            return

        # Return the normal file model if the expression is blank
        if not expression.strip():
            self.model_and_resize(viewed.file.data)
            return

        try:
            # Apply the expression to a variable before committing it to the model
            filtered_data = viewed.file.data.query(expression)
            self.model_and_resize(filtered_data)
        except Exception:
            self.invalid_filter_expression = True
            self.warn_of_expression_error()

    @pyqtSlot()
    def update_percentile_steps(self, refresh: bool = True) -> None:
        """Update percentile sample label with each widget update.

        Args:
            * refresh (bool, optional): Whether the percentile plot widget should be refreshed after
            these updates are performed. This should only be set to False during initialization.
        """
        pct_start: float = self.spin_percentile_start.value()
        pct_end: float = self.spin_percentile_end.value()
        pct_step: float = self.spin_percentile_step.value()

        self.label_percentile_total_samples.setText(
            f"Total Samples: {abs(1 + ((pct_end - pct_start) // pct_step)):,.0f}"
        )

        if refresh and hasattr(self, "plots"):
            PlotObject.update_all_curves("Percentiles")
            self.plots["Percentiles"].autoRange()

    def curve_was_clicked(self) -> None:
        """Function collection related to curve sigClicked events."""
        self.list_loaded_files.emphasize_selected_file()
        self.order_experience_plots()

    @stopwatch(silent=True)
    def add_plot(self, plot_name: str, new_data: Any) -> None:
        """Add the plot of a capture file to a pyqtgraph widget."""
        # Skip undefined curves
        if new_data is None:
            return

        try:
            self.plots[plot_name].addItem(new_data)
            new_data.sigClicked.connect(self.curve_was_clicked)
        except Exception as e:
            logger.error(f"{plot_name} plot was not drawn ({e})")
            log_exception(logger, e, "Failed to draw plot")
