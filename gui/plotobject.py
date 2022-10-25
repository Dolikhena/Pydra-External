"""This module is responsible for creating, tracking, and updating loaded files."""

from pathlib import Path
from typing import Any, Callable, Generator, Optional

from core.configuration import session, set_session_value, setting, setting_bool
from core.exceptions import FileIntegrityError
from core.fileloader import FileLoader
from core.logger import get_logger, log_exception, log_table
from core.stopwatch import stopwatch
from core.utilities import (
    default_data_sources,
    numeric_table_headers,
    stat_table_headers,
    table_indices,
    time_scale,
    time_str_long,
    time_str_short,
)
from formats.capturefile import CaptureFile, InspectionItem
from formats.integrity import Integrity
from numpy import (
    abs,
    any,
    array,
    corrcoef,
    divide,
    errstate,
    histogram,
    isfinite,
    isinf,
    isnan,
    linspace,
    max,
    mean,
    min,
    nan_to_num,
    ndarray,
    percentile,
    repeat,
    unique,
    zeros,
)

from gui.colors import adjust_alpha, restore_color, vendor_color
from gui.metadata import record_exists, update_record
from gui.pyqtgraph.plotdataitem import (
    ClickableBarGraphItem,
    ClickableErrorBarItem,
    OutlierDataItem,
    UnclickableBarGraphItem,
)
from pyqtgraph import PlotDataItem, mkPen

logger = get_logger(__name__)


def str_to_float(value) -> float:
    """Strip all float-invalid characters from a string."""
    if isinstance(value, (int, float)):
        return value
    convert = value.replace(",", "")
    return float(convert.replace("%", ""))


class PlotObject:
    """Class containing data and metadata for a single loaded file."""

    _all_table_headers: dict[str, tuple] = stat_table_headers()
    _cache_hits: dict[str, list] = {
        "Time": [0, 0],
        "Display": [0, 0],
        "Performance": [0, 0],
        "Percentiles": [0, 0],
        "Relative Percentiles": [0, 0],
        "Stutter": [0, 0],
        "Hardware": [0, 0],
    }
    _instances: dict[str, object] = {}
    _numeric_table_headers: list[str] = numeric_table_headers()
    _table_indices = table_indices()
    _valid_instances: dict[str, object] = {}

    compare_against_file: str = "None"
    legend_order: list = []
    unique_data_sources: list[str] = []

    @classmethod
    def report_cache_stats(cls) -> None:
        """Report cache statistics at the end of the session."""
        table_headers = ("Statistics Cache", "Hits", "Total", "Hit Rate")
        report_table: dict[str, tuple] = {
            k: (
                f"{v[0]:,}",
                f"{v[1]:,}",
                f"{v[0] / v[1]:,.1%}" if v[1] > 0 else "---",
            )
            for k, v in cls._cache_hits.items()
        }
        log_table(logger, report_table, table_headers)

    @classmethod
    def all_keys(cls) -> list[str]:
        """Return all PlotObject instance file paths."""
        return list(cls._instances.keys())

    @classmethod
    def all_values(cls) -> list[object]:
        """Return all PlotObject instance objects."""
        return list(cls._instances.values())

    @classmethod
    def valid_objects(cls) -> dict[str, object]:
        """Return pairs from the PlotObject class instance dictionary belonging to valid files."""
        return cls._valid_instances

    @classmethod
    def valid_keys(cls) -> list[str]:
        """Return file names for valid files from the PlotObject class instance dictionary."""
        return list(cls._valid_instances.keys())

    @classmethod
    def valid_values(cls) -> list:
        """Return object IDs for valid files from the PlotObject class instance dictionary."""
        return list(cls._valid_instances.values())

    @classmethod
    def plotted_keys(cls) -> list[str]:
        """Return file names for valid files from the PlotObject class instance dictionary."""
        return [k for k, v in cls._valid_instances.items() if v.plotted]

    @classmethod
    def plotted_values(cls) -> list:
        """Return object IDs for valid files from the PlotObject class instance dictionary."""
        return [v for v in cls._valid_instances.values() if v.plotted]

    @classmethod
    def update_headers(cls) -> None:
        """Update class variables with current table headers."""
        cls._all_table_headers = stat_table_headers()
        cls._table_indices = table_indices()
        cls._numeric_table_headers = numeric_table_headers()

    @classmethod
    def get_by_path(cls, path) -> Optional[object]:
        """Fetch a specific PlotObject instance using file path."""
        return cls._instances.get(str(path), None)

    @classmethod
    def get_by_curve(cls, pdi: object) -> Optional[object]:
        """Fetch a specific PlotObject instance using object instance."""
        for file, plot_obj in cls.valid_objects().items():
            if pdi in plot_obj.curves.values():
                return cls._instances.get(file, None)

    @classmethod
    def get_selected(cls) -> Optional[object]:
        """Fetch a specific PlotObject instance using file path."""
        return cls.get_by_path(session("SelectedFilePath"))

    @classmethod
    def reposition_legend(cls, plot_obj, value: int = 0, relative: bool = False) -> None:
        """Reposition a plot object within the plot legends and stats table."""
        current = cls.legend_order.index(plot_obj)

        if relative:
            value = min(current + value, 0)

        if current == value:
            return  # Already at the desired position
        elif value == -1 and not relative:
            # Move to bottom
            cls.legend_order.append(cls.legend_order.pop(current))
        else:
            cls.legend_order.insert(value, cls.legend_order.pop(current))

    @classmethod
    def clear_plots(cls, deselect: bool = True) -> None:
        """Remove all valid files from plot views."""
        for plot_obj in cls.valid_values():
            plot_obj.plotted = False

        if deselect:
            cls.reset_selection()

    @classmethod
    def remove_all_objects(cls) -> None:
        """Reset the PlotObject class instance dictionary."""
        cls._instances = {}
        cls._valid_instances = {}

        cls.legend_order = []
        cls.reset_selection()
        cls.unique_data_sources = []

    @classmethod
    def update_all_curves(cls, target_plot: str = "") -> None:
        """Refresh the curve data of plotted files, usually in response to time axis changes.

        This approach is faster and less disruptive compared to removing/disconnecting each curve,
        defining a new updated curve object, then adding the new curve back to the originating plot.
        This has the added benefit of preserving the order of legend items while dragging a curve.

        Args:
            * target_plot (str, optional): Name of a specific plot type that will be updated.
            Defaults to "", which updates all plot types.
        """
        for plot_obj in cls.plotted_values():
            plot_obj.define_curves(target_plot)

    @classmethod
    def update_stutter_metrics(cls, plot_obj: object = None) -> None:
        """Reevaluate stutter metrics for a single valid file."""
        if plot_obj is None:
            if cls.get_selected() is None:
                return
            plot_obj = cls.get_selected()

        plot_obj.file.stutter(overwrite=True)
        plot_obj.update_stutter_stats()

    @classmethod
    def update_all_stutter_metrics(cls) -> None:
        """Reevaluate stutter metrics for all valid files."""
        for plot_obj in cls.plotted_values():
            cls.update_stutter_metrics(plot_obj)

    @classmethod
    def update_time_metrics(cls, plot_obj: object = None) -> None:
        """Reevaluate time metrics for a single valid file."""
        if plot_obj is None:
            if cls.get_selected() is None:
                return
            plot_obj = cls.get_selected()
        plot_obj.update_time_stats()

    @classmethod
    def update_all_time_metrics(cls) -> None:
        """Reevaluate time metrics for all valid files."""
        for plot_obj in cls.plotted_values():
            cls.update_time_metrics(plot_obj)

    @classmethod
    def plotted_files_with_data(cls) -> Generator:
        """Return a generator consisting of currently plotted files with valid data."""
        return (
            plot_obj.file
            for plot_obj in cls.valid_objects().values()
            if plot_obj.plotted and plot_obj.plottable_source
        )

    @classmethod
    def reset_file_time(cls, all_files: bool) -> None:
        """Redefine the time range for a dropped file or when trimming from the context menu."""
        if not all_files:
            cls.get_selected().file.reset_time_axis()
        else:
            for plot_obj in cls.plotted_files_with_data():
                plot_obj.reset_time_axis()

    @classmethod
    def zero_file_time(cls, all_files: bool) -> None:
        """Redefine the time range for a dropped file or when trimming from the context menu."""
        if not all_files:
            cls.get_selected().file.start_time_at_zero()
        else:
            for plot_obj_file in cls.plotted_files_with_data():
                plot_obj_file.start_time_at_zero()

    @classmethod
    def trim_file_time(cls, all_files: bool, relation: str, cutoff: float) -> None:
        """Redefine the time range for a dropped file or when trimming from the context menu."""
        if all_files:
            for plot_obj_file in cls.plotted_files_with_data():
                plot_obj_file.trim_time_axis(relation=relation, cutoff=cutoff)

        elif not cls.get_selected():
            return
        else:
            cls.get_selected().file.trim_time_axis(relation=relation, cutoff=cutoff)

    @classmethod
    def adjust_alpha_by_selection(cls) -> None:
        """Temporarily adjust plot alpha values based on file selection."""
        emphasized: int = int(setting("Plotting", "EmphasizedAlpha"))
        diminished: int = int(setting("Plotting", "DiminishedAlpha"))

        if session("SelectedFilePath") == "":
            cls.reset_all_pen_colors()
        else:
            for file_path, plot_obj in cls.valid_objects().items():
                selected: bool = file_path == session("SelectedFilePath")
                rgb: tuple = plot_obj.pen[:3]
                plot_obj.pen = rgb + ((emphasized,) if selected else (diminished,))
                cls.update_object_pen(plot_obj)

    @classmethod
    def update_pen_alpha_values(cls, new_alpha: int) -> None:
        """Update plot alpha values for normal plots by user-defined value."""
        for plot_obj in cls.valid_values():
            plot_obj.pen = plot_obj.pen[:3] + (new_alpha,)
            cls.update_object_pen(plot_obj)

    @classmethod
    def select_by_path(cls, selection_path: str) -> None:
        """Adjust pen colors for curves based on file path."""
        # Reset all pens if the selected plot object has been reselected
        if selection_path != "" and selection_path == session("SelectedFilePath"):
            cls.reset_selection()
        else:
            # Emphasize alpha of selected file's plots while diminishing others
            set_session_value("SelectedFilePath", selection_path)
            cls.adjust_alpha_by_selection()

    @classmethod
    def select_by_curve(cls, selection: object) -> Optional[str]:
        """Adjust pen colors for curves based on selection."""
        selected_file = (
            cls.select_by_path(file)
            for file, plot_obj in cls.valid_objects().items()
            if selection in plot_obj.curves.values()
        )
        return next(selected_file, None)

    @staticmethod
    def update_object_pen(plot_obj: object) -> None:
        """Match a file's plot curve pen colors to new color values."""
        files_with_curves = ((k, v) for k, v in plot_obj.curves.items() if v)
        new_brush: tuple = plot_obj.brush
        new_pen: tuple = mkPen(plot_obj.pen, width=plot_obj.width)

        for pair in files_with_curves:
            plot_type, pdi = pair

            if plot_type in {"Outliers", "Scatter"}:
                pdi.setSymbolBrush(new_brush)
                pdi.setSymbolPen(new_pen)
                continue
            elif plot_type in {"Histogram", "Box", "Experience"}:
                pdi.setBrush(new_brush)
            pdi.setPen(new_pen)

    @classmethod
    def update_selected_pen(cls) -> None:
        """Update the selected file's plot curve pen colors and reset the selection."""
        if cls.get_selected():
            cls.update_object_pen(cls.get_selected())
            cls.reset_selection()

    @classmethod
    def reset_selection(cls) -> None:
        """Return all plot curve pen alphas to normal values and default selected_file."""
        set_session_value("SelectedFilePath", "")
        cls.reset_all_pen_colors()

    @classmethod
    def reset_all_pen_colors(cls) -> None:
        """Revert all plot alphas to the normal (non-emphasized) value."""
        new_alpha: tuple = (int(setting("Plotting", "NormalAlpha")),)
        for plot_obj in cls.valid_values():
            plot_obj.pen = plot_obj.pen[:3] + new_alpha
            cls.update_object_pen(plot_obj)

    __slots__ = (
        "_brush",
        "_hashes",
        "_pen",
        "_plotted",
        "_sources",
        "_width",
        "curves",
        "file",
        "legend_name",
        "plottable_source",
        "plottable_scatter",
        "r_squared",
        "stats",
    )

    def __init__(self, path: Path, callback: Optional[Callable] = None) -> None:
        """Container object for a loaded capture file.

        This is an interface between the GUI window and supported capture types (e.g., FrameView,
        PCAT, HWiNFO, etc.).

        Args:
            * path (Path): `Path` object pointing to the file's location on the disk. This is passed
            on to other functions as a str since `Path` strings can be interpreted just the same.
        """
        self._brush: tuple
        self._hashes: dict
        self._pen: tuple
        self._plotted: bool = False
        self._sources: dict
        self._width: int
        self.curves: dict[str, object]
        self.file: CaptureFile
        self.legend_name: str
        self.plottable_source: bool
        self.plottable_scatter: bool
        self.r_squared: str
        self.stats: list[str]

        self.create_plot_object(path, callback)

    @stopwatch(silent=True)
    def create_plot_object(self, path: Path, callback: Optional[Callable] = None) -> None:
        """Initialize an object regardless of its capture type or validity."""
        try:
            self.file = FileLoader(path, callback).infer_format()

            if self.file.integrity.valid():
                return self.full_object_setup()

            # Catch any files that couldn't be processed by their modules
            self.file.app_name = "Unknown"
            raise FileIntegrityError("Encountered an unexpected error during processing")
        except RuntimeError:
            logger.error("PlotObject was destroyed unexpectedly")
        except Exception as e:
            log_exception(logger, e, "Failed to create PlotObject")
            self.file.integrity = Integrity.Invalid
        finally:
            # Update the generic PlotObject class dict with this instance
            PlotObject._instances[str(path)] = self

    @stopwatch(silent=True)
    def full_object_setup(self) -> None:
        """Initialize all functional instance variables for a valid capture."""
        try:
            self._hashes = {
                "Time": 0,
                "Display": 0,
                "Performance": 0,
                "Percentiles": 0,
                "Relative Percentiles": 0,
                "Stutter": 0,
                "Hardware": 0,
            }
            self._sources = {
                "Frame Time (ms)": (self.file.frametimes, []),
                "Frame Rate (fps)": (self.file.frametimes, [True]),
                "Interframe Variation (ms)": (self.file.frame_variation, []),
                "Stutter (%)": (self.file.stutter, []),
                "Total Board Power (W)": (self.file.power, ["GPU Board"]),
                "Graphics Chip Power (W)": (self.file.power, ["GPU Chip"]),
                "Perf-per-Watt (F/J)": (self.file.perf_per_watt, ["GPU Board"]),
                "System Latency (ms)": (self.file.latency, []),
                "GPU Temperature (°C)": (self.file.temperature, ["GPU"]),
                "GPU Frequency (MHz)": (self.file.frequency, ["GPU"]),
                "GPU Utilization (%)": (self.file.utilization, ["GPU"]),
                "GPU Voltage (V)": (self.file.voltage, ["GPU"]),
                "CPU Power (W)": (self.file.power, ["CPU"]),
                "CPU Temperature (°C)": (self.file.temperature, ["CPU"]),
                "CPU Frequency (MHz)": (self.file.frequency, ["CPU"]),
                "CPU Utilization (%)": (self.file.utilization, ["CPU"]),
                "Battery Charge Rate (W)": (self.file.battery_charge_rate, []),
                "Battery Level (%)": (self.file.battery_level, []),
            }
            self.curves = {
                "Line": None,
                "Percentiles": None,
                "Histogram": None,
                "Box": None,
                "Error": None,
                "Outliers": None,
                "Scatter": None,
                "Experience": None,
            }
            self.stats = []

            # Search and restore the file's color record if it exists, otherwise generate the color
            self._width = 1  # TODO: Restore from metadata
            self._pen = self._brush = (
                restore_color(self.file.hash)
                if record_exists(self.file.hash, "Color")
                else vendor_color(self.file.properties["GPU"])
            )

            self.file.valid_file_setup()
            self.collect_file_headers()
            self.calculate_stats()

            if self.file.properties["Legend"][0]:
                self.legend_name = self.file.properties["Legend"][1]

            # Update the (valid) PlotObject class dict with this instance
            PlotObject._valid_instances[str(self.file.path)] = self
            PlotObject.legend_order.append(self)
        except Exception as e:
            log_exception(logger, e, "Failed to create valid PlotObject")
            raise FileIntegrityError(f"Failed to create valid object for {self.file.path}") from e

    @property
    def brush(self) -> tuple[int, int, int, int]:
        """Return this file's RGBA brush color with diminished alpha component."""
        return adjust_alpha(self._brush, 0.5)

    @brush.setter
    def brush(self, rgba: tuple[int, int, int, int]) -> None:
        """Set this file's brush color."""
        self._brush = rgba

    @property
    def pen(self) -> tuple[int, int, int, int]:
        """Return this file's RGBA pen color."""
        return self._pen

    @pen.setter
    def pen(self, rgba: tuple[int, int, int, int]) -> None:
        """Set this file's pen and brush colors."""
        # Add alpha component if it's missing
        if len(rgba) == 3:
            rgba = rgba + (self._pen[3],)

        if self._pen[:3] != rgba[:3]:
            update_record(
                self.file.hash, {"R": int(rgba[0]), "G": int(rgba[1]), "B": int(rgba[2])}, "Color"
            )
        self._pen = self.brush = rgba

    @property
    def width(self) -> int:
        """Return this file's pen width."""
        return self._width

    @width.setter
    def width(self, new_width: int) -> None:
        """Set this file's pen and brush colors."""
        self._width = new_width

    @property
    def plotted(self) -> bool:
        """Return if this file is currently plotted."""
        return self._plotted

    @plotted.setter
    def plotted(self, is_plotted: bool) -> None:
        """Set this file's plotted status.

        If the file is about to be plotted, its plot curve items will be (re-)calculated.
        """
        if is_plotted:
            self.define_curves()
        self._plotted = is_plotted

    def collect_file_headers(self) -> None:
        """Collect headers from all valid loaded files to make them available as data sources."""
        merged_headers: list[str] = list(
            dict.fromkeys(PlotObject.unique_data_sources + self.file.headers)
        )

        if len(merged_headers) != len(PlotObject.unique_data_sources):
            merged_headers.sort()
            PlotObject.unique_data_sources = merged_headers

    @stopwatch(silent=True)
    def update_time_stats(self) -> None:
        """Force update time-based metrics for a file, usually in response to trimming."""
        try:
            self.set_time_metrics()
        except Exception as e:
            log_exception(logger, e, "Failed to compute time stats")

    @stopwatch(silent=True)
    def update_stutter_stats(self) -> None:
        """Force update stutter metrics for a file, usually in response to trimming."""
        try:
            self.set_stutter_metrics()
        except Exception as e:
            log_exception(logger, e, "Failed to compute stutter stats")

    @stopwatch(silent=True)
    def calculate_stats(self) -> None:
        """Compute fields for the statistics table when a file is plotted."""
        if self.stats == []:
            self.stats = ["N/A"] * len(PlotObject._all_table_headers)

        try:
            self.set_capture_metrics()
            self.set_time_metrics()
            self.set_display_metrics()
            self.set_performance_metrics()
            self.set_percentile_metrics()
            self.set_relative_percentile_metrics()
            self.set_stutter_metrics()
            self.set_hardware_metrics()
        except Exception as e:
            log_exception(logger, e, "Failed to compute file stats")

    def use_cached_stats(self, section: str, other_criteria: tuple = (None,)) -> bool:
        """Return if the hash value for a given section has changed.

        By default this checks if the start/end of a file has changed, but other criteria can be
        provided in a tuple.
        """
        try:
            PlotObject._cache_hits[section][1] += 1
            range_hash: int = hash(
                (
                    self.file.offset,
                    self.file.height,
                    *other_criteria,
                ),
            )

            if self._hashes.get(section, None) == range_hash:
                PlotObject._cache_hits[section][0] += 1
                return True

            self._hashes[section] = range_hash
            return False
        except Exception as e:
            log_exception(logger, e, "Failed to compute stats hash")
            return True  # Default to recalculating stats

    def get_stat(self, header: str = "") -> Any:
        """Return a cell value from the statistics table."""
        if header in stat_table_headers():
            return self.stats[PlotObject._table_indices(header)]
        return logger.error(f"Invalid stat table header: {header}")

    def set_stat(self, header: str = "", value: Any = "N/A") -> None:
        """Set a cell's value (referenced by header) in the statistics table."""
        self.stats[PlotObject._table_indices(header)] = value

    @stopwatch(silent=True)
    def get_all_stats(self) -> list[str]:
        """Return a list of raw or relative statistics."""
        if PlotObject.compare_against_file == "None":
            return self.stats

        base_file_stats: Callable = PlotObject.get_by_path(PlotObject.compare_against_file).stats
        relative_stats: list[str] = ["N/A"] * len(PlotObject._all_table_headers)
        precision: int = int(setting("General", "DecimalPlaces"))

        base_stat: float = 0
        file_stat: float = 0
        difference: float = 0
        sign: str = ""

        for idx, name in enumerate(PlotObject._all_table_headers):
            if name in PlotObject._numeric_table_headers:
                if self.file.path == PlotObject.compare_against_file:
                    relative_stats[idx] = "—"
                else:
                    try:
                        base_stat = str_to_float(base_file_stats[idx])
                        file_stat = str_to_float(self.stats[idx])
                        difference = (file_stat - base_stat) / base_stat
                        sign = "+" if difference > 0 else ""
                        relative_stats[idx] = f"{sign}{difference:,.{precision}%}"
                    except Exception:
                        relative_stats[idx] = "N/A"
            else:
                relative_stats[idx] = self.stats[idx]
        return relative_stats

    @stopwatch(silent=True)
    def set_capture_metrics(self) -> None:
        """Set the capture metadata statistics.

        These fields are not hashed and so are updated with every call.
        """
        try:
            self.set_stat("Capture\nType", f"{self.file.app_name} v{self.file.version}")
            self.set_stat("Capture\nIntegrity", self.file.integrity.name)
            self.set_stat("Application", self.file.properties["Application"])
            self.set_stat("Resolution", self.file.properties["Resolution"])
            self.set_stat("Runtime", self.file.properties["Runtime"])
            self.set_stat("GPU", self.file.properties["GPU"])
            self.set_stat("Comments", self.file.properties["Comments"])
            self.set_stat("File Name", str(self.file.name))
            self.set_stat("File Location", str(self.file.path))
        except ValueError as e:
            log_exception(logger, e, "Metadata key lookup failed")
        except Exception as e:
            log_exception(logger, e)

    @stopwatch(silent=True)
    def set_time_metrics(self) -> None:
        """Set the capture's time-related statistics.

        These fields are hashed using the default criteria.
        """
        _time_scale = time_scale()
        if not self.file.alias_present("Elapsed Time") or self.use_cached_stats(
            "Time", (_time_scale,)
        ):
            return

        try:
            time: ndarray = self.file.elapsed_time()

            self.set_stat(f"Duration {time_str_short()}", (max(time) - min(time)) / _time_scale)

            battery_charge_data = self.file.alias_present("Battery Charge Rate")
            battery_level_data: bool = self.file.alias_present("Battery Level")
            battery_header: str = f"Projected\nBattery Life {time_str_short()}"

            if (
                battery_charge_data
                and battery_level_data
                and (projection := self.file.project_battery_life()) > 0
            ):
                self.set_stat(battery_header, projection / _time_scale)
        except ValueError as e:
            log_exception(logger, e, "Time calculation failed")
        except Exception as e:
            log_exception(logger, e)

    @stopwatch(silent=True)
    def set_display_metrics(self) -> None:
        """Set the capture display statistics.

        These fields are hashed using the default criteria and decimal place.
        """
        precision: int = int(setting("General", "DecimalPlaces"))
        if self.use_cached_stats("Display", (precision,)):
            return

        try:
            self.set_stat("Number\nof Frames", f"{self.file.frames():,}")

            if self.file.alias_present("Unsynchronized Frames"):
                self.set_stat(
                    "Synced\nFrames", f"{1 - mean(self.file.unsynced_frames()):.{precision}%}"
                )
        except ValueError as e:
            log_exception(logger, e, "Display calculation failed")
        except Exception as e:
            log_exception(logger, e)

    @stopwatch(silent=True)
    def set_performance_metrics(self) -> None:
        """Set the capture performance statistics.

        These fields are hashed using the default criteria.
        """
        if self.file.tainted_frametimes() or self.use_cached_stats("Performance"):
            return

        try:
            frametimes: ndarray = self.file.frametimes()
            self.set_stat("Average FPS", 1000 / mean(frametimes))
            self.set_stat("Minimum FPS", 1000 / max(frametimes))
            self.set_stat("Maximum FPS", 1000 / min(frametimes))
        except ValueError as e:
            log_exception(logger, e, "Perf calculation failed")
        except Exception as e:
            log_exception(logger, e)

    @stopwatch(silent=True)
    def set_percentile_metrics(self) -> None:
        """Set the frame time percentile statistics.

        These fields are hashed using the default criteria and percentile method.
        """
        exclusive_percentiles: bool = setting("Statistics", "PercentileMethod") == "Exclusive"
        if self.file.tainted_frametimes() or self.use_cached_stats(
            "Percentiles", (exclusive_percentiles,)
        ):
            return

        try:
            frametimes: ndarray = self.file.frametimes()
            q_mod: float = int(exclusive_percentiles) * (1 / (len(frametimes) + 1)) * 100

            def fps_percentile(q: float) -> float:
                """Return the inclusive or exclusive fps percentile for a given rank."""
                try:
                    if exclusive_percentiles and q != 50:
                        q = min([q + q_mod, 100]) if q > 50 else max([0, q - q_mod])
                    return 1000 / percentile(frametimes, q=q)
                except Exception:
                    return "N/A"

            # Traditional percentiles
            self.set_stat("0.1% FPS", fps_percentile(99.9))
            self.set_stat("1% FPS", fps_percentile(99))
            self.set_stat("5% FPS", fps_percentile(95))
            self.set_stat("10% FPS", fps_percentile(90))
            self.set_stat("Median FPS", fps_percentile(50))

            # Low FPS percentiles
            self.set_stat(
                "0.1% Low FPS",
                1000 / mean(frametimes[frametimes >= 1000 / self.get_stat("0.1% FPS")]),
            )
            self.set_stat(
                "1% Low FPS", 1000 / mean(frametimes[frametimes >= 1000 / self.get_stat("1% FPS")])
            )
        except ValueError as e:
            log_exception(logger, e, "Percentile calculation failed")
        except Exception as e:
            log_exception(logger, e)

    @stopwatch(silent=True)
    def set_relative_percentile_metrics(self) -> None:
        """Set the relative frame time percentile statistics.

        These fields are hashed using the default criteria and decimal place.
        """
        precision: int = int(setting("General", "DecimalPlaces"))
        if self.file.tainted_frametimes() or self.use_cached_stats(
            "Relative Percentiles", (precision,)
        ):
            return

        try:
            avg_fps: float = self.get_stat("Average FPS")

            def relative_fps(pct: str) -> str:
                percentile: Any = self.get_stat(f"{pct} FPS")
                try:
                    if isinstance(percentile, str):
                        return "N/A"
                    return f"{(percentile / avg_fps) - 1:,.{precision}%}"
                except Exception:
                    return "N/A"

            self.set_stat("0.1% Low FPS\n/ Average FPS", relative_fps("0.1% Low"))
            self.set_stat("0.1% FPS\n/ Average FPS", relative_fps("0.1%"))
            self.set_stat("1% Low FPS\n/ Average FPS", relative_fps("1% Low"))
            self.set_stat("1% FPS\n/ Average FPS", relative_fps("1%"))
            self.set_stat("5% FPS\n/ Average FPS", relative_fps("5%"))
            self.set_stat("10% FPS\n/ Average FPS", relative_fps("10%"))
        except ValueError as e:
            log_exception(logger, e, "Relative percentile calculation failed")
        except Exception as e:
            log_exception(logger, e)

    @stopwatch(silent=True)
    def set_stutter_metrics(self) -> None:
        """Set the capture stutter statistics.

        These fields are hashed using the default criteria and decimal place.
        """
        precision: int = int(setting("General", "DecimalPlaces"))
        if self.use_cached_stats("Stutter", (precision,)):
            return

        try:
            stutter = self.file.stutter()
            osc: bool = stutter.average == "OSC"

            self.set_stat("Number of\nStutter Events", f"{stutter.total:,}")
            self.set_stat("Proportion\nof Stutter", f"{stutter.proportional:.{precision}%}")
            self.set_stat(
                "Average\nStutter",
                stutter.average if osc else f"{stutter.average:,.{precision}%}",
            )
            self.set_stat(
                "Maximum\nStutter",
                stutter.max if osc else f"{stutter.max:,.{precision}%}",
            )
        except ValueError as e:
            log_exception(logger, e, "Stutter calculation failed")
        except Exception as e:
            log_exception(logger, e)

    @stopwatch(silent=True)
    def set_hardware_metrics(self) -> None:
        """Set the system hardware metadata statistics.

        These fields are hashed using the default criteria.
        """
        if self.use_cached_stats("Hardware"):
            return

        try:
            # Hardware metrics that only need to be checked for presence
            for alias, values in self.alias_header_mappings().items():
                header, metric = values
                if self.file.alias_present(alias):
                    self.set_stat(header, mean(metric))

            self.set_power_metrics()
        except ValueError as e:
            log_exception(logger, e, "Hardware calculation failed")
        except Exception as e:
            log_exception(logger, e)

    def set_power_metrics(self):
        """Set the system power metrics."""
        # FrameView does not have a general GPU power column
        aliases: tuple = tuple(self.file.aliases(self.file.version).keys())

        if self.file.power("GPU Board") is not None:
            board_power: float = mean(self.file.power("GPU Board"))
            valid_board_power: bool = (
                board_power > 0 and any("GPU Board" in alias for alias in aliases)
                if self.file.app_name == "FrameView"
                else self.file.alias_present("GPU Board")
            )

            if valid_board_power:
                self.set_stat("Average GPU\nBoard Power (W)", board_power)

                ppw = self.file.perf_per_watt("GPU Board")
                if min(ppw) > 0:
                    self.set_stat("Average Perf-\nper-Watt (F/J)", mean(ppw))

        if self.file.power("GPU Chip") is not None:
            chip_power: float = mean(self.file.power("GPU Chip"))
            valid_chip_power: bool = (
                chip_power > 0 and any("GPU Chip" in alias for alias in aliases)
                if self.file.app_name == "FrameView"
                else self.file.alias_present("GPU Chip")
            )
            if valid_chip_power:
                self.set_stat("Average GPU\nChip Power (W)", chip_power)

    def alias_header_mappings(self) -> dict[str, tuple]:
        """Return a dictionary corresponding to a general alias's stat header and method."""
        return {
            "System Latency": ("Average System\nLatency (ms)", self.file.latency()),
            "GPU Frequency": ("Average GPU\nFrequency (MHz)", self.file.frequency("GPU")),
            "GPU Temperature": ("Average GPU\nTemperature (°C)", self.file.temperature("GPU")),
            "GPU Utilization": ("Average GPU\nUtilization (%)", self.file.utilization("GPU")),
            "GPU Voltage": ("Average GPU\nVoltage (V)", self.file.voltage("GPU")),
            "CPU Power": ("Average CPU\nPower (W)", self.file.power("CPU")),
            "CPU Frequency": ("Average CPU\nFrequency (MHz)", self.file.frequency("CPU")),
            "CPU Temperature": ("Average CPU\nTemperature (°C)", self.file.temperature("CPU")),
            "CPU Utilization": ("Average CPU\nUtilization (%)", self.file.utilization("CPU")),
            "Battery Charge Rate": (
                "Average Battery\nCharge Rate (W)",
                self.file.battery_charge_rate(),
            ),
        }

    def color_marked_properties(self, property_name: str) -> str:
        """Inspect property values and generate HTML to highlight questionable properties in tooltips."""
        property_value = self.file.properties[property_name]

        if "*" in property_value:
            return f"<font color='red'><b>{property_value}</b></font>"

        return property_value

    @stopwatch(silent=True)
    def tooltip(self) -> str:
        """Produce a tooltip using the file properties, or if not valid, the integrity description."""
        tooltip_text: str = self.file.integrity.description()

        if not self.file.integrity.valid():
            return f"<span>{tooltip_text}</span>"

        concerns: tuple = (
            self.file.duplicate_headers is not None,
            not self.file.alias_in_headers("Elapsed Time"),
            not self.file.alias_in_headers("Frametimes"),
            self.file.tainted_frametimes(),
            hasattr(self.file, "MAJOR_INSPECTION_ITEMS") and not self.file.passed_inspection(),
        )

        tooltip_text += self.tooltip_metadata()
        tooltip_text += self.tooltip_basic_stats(concerns)

        if not any(concerns):
            return f"<span>{tooltip_text}</span>"
        elif "<font color='red'>" in tooltip_text:
            tooltip_text += """<br><br>* Inconsistencies or problematic values<br>
            identified in fields <font color='red'><b>highlighted in red</b></font>."""

        tooltip_text += self.tooltip_major_issues(concerns)
        return f"<span>{tooltip_text}</span>"

    def tooltip_major_issues(self, concerns: tuple) -> str:
        duplicate_headers, missing_time, missing_fps, tainted_fps, inspection_issues = concerns
        text: str = "<br><br><b>Capture Inspection:</b>"
        red_x: str = "<br> ❌ "

        if duplicate_headers:
            text += f"{red_x}Duplicate column headers ({len(self.file.duplicate_headers)})"

        if missing_time:
            text += f"{red_x}Does not contain time data"

        if missing_fps:
            text += f"{red_x}Does not contain performance data"
        elif tainted_fps:
            text += f"{red_x}Zeroes or invalid values in performance data"

        if inspection_issues:
            text += self.tooltip_inspection(red_x)

        return text

    def tooltip_metadata(self):
        """Generate a text block of the file's metadata."""
        text: str = (
            f"<br><br><b>Capture Software</b>: {self.file.app_name} {self.file.version}<br>"
            f"<b>Application</b>: {self.color_marked_properties('Application')}<br>"
            f"<b>Resolution</b>: {self.color_marked_properties('Resolution')}<br>"
            f"<b>Runtime</b>: {self.color_marked_properties('Runtime')}<br>"
            f"<b>GPU</b>: {self.color_marked_properties('GPU')}<br>"
            f"<b>Comments</b>: {self.color_marked_properties('Comments')}"
        )

        if self.file.properties["Legend"][0]:
            text += f"<br><b>Legend</b>: {self.file.properties['Legend'][1]}"

        return text

    def tooltip_basic_stats(self, concerns: tuple):
        """Generate a text block of some basic statistics."""
        try:
            # TODO: Update on file alterations and changes to decimal places or time scale
            _, missing_time, missing_fps, tainted_fps, _ = concerns

            # Elapsed time
            text: str = "<br><br><b>Duration</b>: "
            if missing_time:
                text += "<font color='red'><b>N/A</b></font>"
            else:
                precision: int = int(setting("General", "DecimalPlaces"))
                time_scale: str = time_str_long()
                text += (
                    f"{self.get_stat(f'Duration {time_str_short()}'):,.{precision}f} {time_scale}"
                )

            # Performance
            text += "<br><b>Average FPS</b>: "
            avg_fps: str = self.get_stat("Average FPS")
            low_fps: str = self.get_stat("1% Low FPS")

            if avg_fps != "N/A":
                avg_fps = f"{avg_fps:,.{precision}f}"

            if low_fps != "N/A":
                low_fps = f"{low_fps:,.{precision}f}"

            if missing_fps:
                text += (
                    "<font color='red'><b>N/A</b></font>"
                    "<br><b>1% Low FPS</b>: <font color='red'><b>N/A</b></font>"
                )
            elif tainted_fps:
                text += (
                    f"<font color='red'><b>{avg_fps}*</b></font>"
                    f"<br><b>1% Low FPS</b>: <font color='red'><b>{low_fps}</b></font>"
                )
            else:
                text += f"{avg_fps}" f"<br><b>1% Low FPS</b>: {low_fps}"
        except Exception as e:
            log_exception(logger, e)
            text = "<br><br><font color='red'><b>Failed to parse basic stats</b></font>"
        finally:
            return text

    def tooltip_inspection(self, red_x: str) -> str:
        """Append inspection findings to the tooltip, starting with major issues."""
        major_items: dict = self.file.MAJOR_INSPECTION_ITEMS[self.file.version]
        major_tags: str = f"{red_x}<b>Warning</b>: "
        minor_tags: str = "<br> ⚠ <b>Caution</b>: "
        text: str = ""

        # Qualities that indicate detrimental conditions/qualities of the capture
        major_concerns = (
            (check, result)
            for check, result in self.file.inspection.items()
            if isinstance(result, InspectionItem) and check in major_items and not result.passed
        )
        for check, result in major_concerns:
            if result.violations != -1:
                text += (
                    f"{major_tags}{result.description} ({result.violations:,} "
                    f"frame{'s' if result.violations > 1 else ''}, "
                    f"{result.violations / self.file.frames():.1%})"
                )
            else:
                text += f"{major_tags}{check} field could not be inspected"

        # Qualities that suggest suboptimal conditions/qualities of the capture
        minor_concerns = (
            (check, result)
            for check, result in self.file.inspection.items()
            if isinstance(result, InspectionItem) and check not in major_items and not result.passed
        )
        for check, result in minor_concerns:
            if result.violations != -1:
                text += f"{minor_tags}{result.description}"
            else:
                text += f"{minor_tags}{check} field could not be inspected"

        return text

    @staticmethod
    @stopwatch(silent=True)
    def percentile_range(data: ndarray) -> tuple:
        """Calculate percentiles for a given range and interval."""
        start: float = float(setting("Percentiles", "PercentileStart"))
        end: float = float(setting("Percentiles", "PercentileEnd"))
        step: float = float(setting("Percentiles", "PercentileStep"))
        samples: int = int(abs(1 + ((end - start) // step)))
        pct_range: ndarray = linspace(start, end, samples)

        if session("PrimaryDataSource") == "Stutter (%)" or any(isinf(data)):
            return (pct_range, zeros(samples))
        return (pct_range, percentile(data, pct_range))

    def formatted_legend(self) -> str:
        """Return the translated legend template surrounded by markup tags."""
        text_size: int = int(setting("Plotting", "LegendItemFontSize"))
        return f"<span style='font-size:{text_size}pt;'>{self.legend_name}</span>"

    def translate_legend_name(self, fmt: str = "") -> str:
        """Translate a given string format for legend items based on file metadata."""
        if self.file.properties["Legend"][0]:
            return self.legend_name

        translated_name: str = "N/A"
        try:
            legend_format: str = fmt or setting("Plotting", "LegendItemFormat")
            legend_tags: dict[str, str] = {
                "Application": self.file.properties["Application"],
                "Resolution": self.file.properties["Resolution"],
                "Runtime": self.file.properties["Runtime"],
                "GPU": self.file.properties["GPU"],
                "Comments": self.file.properties["Comments"],
                "FileName": self.file.name,
                "FilePath": self.file.path,
            }

            translated_name = legend_format
            for key, value in legend_tags.items():
                # Be explicit with unknown properties
                if value == "Unknown":
                    value = f"Unknown {key}"
                translated_name = translated_name.replace(f"[{key}]", value)
        except Exception as e:
            log_exception(logger, e, "Failed to translate legend title")

        return translated_name

    @stopwatch(silent=True)
    def source_function_map(self, source_name: str) -> tuple:
        """Resolve an object method from its categorical source name."""
        return self._sources.get(source_name, self.file.column())

    @stopwatch(silent=True)
    def translate_data_source(self, source_name: str) -> ndarray:
        """Provide the relevant array for a given data source category."""
        source_data: ndarray = array([0, 0])
        try:
            if source_name in default_data_sources():
                func, args = self.source_function_map(source_name)
                source_data = func(*args)

                if source_name == "Stutter (%)":
                    source_data = source_data.deviations if source_data.average != "OSC" else []
            else:
                source_data = self.file.column(source_name)
        except Exception as e:
            log_exception(logger, e, f"Failed to obtain {source_name} data")
        else:
            source_data = nan_to_num(source_data, nan=0, posinf=0, neginf=0)

        return source_data

    def validate_data_source(self, data_source: ndarray, source_name: str = "") -> bool:
        """Return a boolean indicating if the source data is suitable for plotting."""
        try:
            plot_empty_data: bool = setting_bool("Plotting", "PlotEmptyData")

            valid_header: bool = (
                source_name in default_data_sources()
                or source_name in self.file.headers
                or plot_empty_data
            )
            unique_header: bool = len(data_source.shape) == 1
            valid_data: bool = plot_empty_data or data_source.any()
            plottable_data: bool = valid_header and unique_header and valid_data

            if not plottable_data:
                return False

            # Test if data contains strings (e.g., "Error" in Dropped column of FV files)
            try:
                isfinite(data_source)
                return True
            except Exception:
                return False
        except Exception:
            return False

    @stopwatch(silent=True)
    def define_curves(self, target_plot: str = "") -> None:
        """Create all of the different plot curves for this file.

        If a valid curve was already defined and the current source data appears to be valid, its
        data will instead be overwritten rather than the curve/legend objects being disconnected,
        removed, redfined, added back, and reconnected.

        Args:
            * target_plot (str, optional): Name of a specific plot type that will be updated.
            Defaults to "", which updates all plot types.
        """
        primary_source: str = session("PrimaryDataSource")
        try:
            self.legend_name = self.translate_legend_name()
            if target_plot == "Legend":
                return

            primary_data: ndarray = self.translate_data_source(primary_source)
            self.plottable_source = self.validate_data_source(primary_data, primary_source)

            # Validate secondary data sources for scatter plot
            secondary_source: str = session("SecondaryDataSource")
            viewing_stutter: bool = "Stutter (%)" in {primary_source, secondary_source}
            self.plottable_scatter = session("EnableScatterPlots") and not viewing_stutter
            secondary_data = None

            if self.plottable_scatter:
                if primary_source == secondary_source:
                    secondary_data = primary_data
                    self.plottable_scatter = self.plottable_source
                else:
                    secondary_data = self.translate_data_source(secondary_source)
                    self.plottable_scatter = self.plottable_source and self.validate_data_source(
                        secondary_data, secondary_source
                    )

            if not self.plottable_source or (
                target_plot == "Scatter" and not self.plottable_scatter
            ):
                return

            curve_funcs: dict[str, tuple[Callable, list]] = {
                "Line": (self.define_line_curve, [primary_source, primary_data]),
                "Percentiles": (self.define_percentile_curve, [primary_source, primary_data]),
                "Histogram": (self.define_histogram_curve, [primary_source, primary_data]),
                "Box": (self.define_box_curve, [primary_source, primary_data]),
                "Scatter": (
                    self.define_scatter_curve,
                    [primary_source, primary_data, secondary_source, secondary_data],
                ),
                "Experience": (self.define_experience_curve, []),
            }

            if target_plot in curve_funcs:
                plot_func, args = curve_funcs[target_plot]
                return plot_func(*args)

            for name, plot_signature in curve_funcs.items():
                if name == "Scatter" and not self.plottable_scatter:
                    continue

                plot_func, args = plot_signature
                plot_func(*args)
        except Exception as e:
            logger.error(f"Failed to create curves for {primary_source}")
            log_exception(logger, e, "Failed to create plot curves")

    @stopwatch(silent=True)
    def define_abstract_curve(self, plot_name: str, curve_kwargs: dict) -> None:
        """Generalized method for defining a curve or serving a cached result.

        Args:
            * plot_name (str): Name of the plot type being defined.
            * curve_kwargs (dict): A dictionary of various plot-specific parameters for the curve.
        """
        curve_type = {
            # "Scatter": ScatterPlotItem,
            "Box": UnclickableBarGraphItem,
            "Error": ClickableErrorBarItem,
            "Outliers": OutlierDataItem,
            "Experience": ClickableBarGraphItem,
        }.get(plot_name, PlotDataItem)

        # Scatter-like plots will connect points with lines if given a pen color
        pen = {
            "Outliers": None,
            "Scatter": None,
        }.get(plot_name, mkPen(self.pen, width=self.width))

        self.curves[plot_name] = curve_type(
            pen=pen,
            clickable=True,
            name=self.legend_name,
            skipFiniteCheck=True,
            **curve_kwargs,
        )
        self.curves[plot_name].sigClicked.connect(self.select_by_curve)

    def updatable_curve(self, plot_name: str) -> bool:
        """Return a boolean indicating if a plot curve can be updated."""
        return self.plotted and self.curves[plot_name] is not None

    @stopwatch(silent=True)
    def define_line_curve(self, primary: str, source_data: ndarray) -> None:
        """Define the line plot curve.

        Args:
            * primary (str): The name of the primary data source. Only used in an Exception.
            * source_data (ndarray): The data that will be used in the curve.
        """
        if not self.file.alias_present("Elapsed Time"):
            return

        try:
            time_data: ndarray = self.file.elapsed_time()

            if len(time_data) != len(source_data):
                return

            plot_name: str = "Line"
            curve_params: dict = {
                "x": time_data,
                "y": source_data,
            }

            # Prefer updating a curve's data rather than recreating a curve object
            if self.updatable_curve(plot_name):
                return self.curves[plot_name].setData(**curve_params)
            return self.define_abstract_curve(plot_name, curve_params)
        except Exception as e:
            logger.error(f"Failed to create line curve for {primary}")
            log_exception(logger, e, "Failed to create line curve")

    @stopwatch(silent=True)
    def define_percentile_curve(self, primary: str, source_data: ndarray) -> None:
        """Define the percentile plot curve.

        Args:
            * primary (str): The name of the primary data source. Only used in an Exception.
            * source_data (ndarray): The data that will be used in the curve.
        """
        try:
            pct_range, pct_source = self.percentile_range(source_data)
            plot_name: str = "Percentiles"
            curve_params: dict = {
                "x": pct_range,
                "y": pct_source,
            }

            if self.updatable_curve(plot_name):
                return self.curves[plot_name].setData(**curve_params)
            return self.define_abstract_curve(plot_name, curve_params)
        except Exception as e:
            logger.error(f"Failed to create percentile curve for {primary}")
            log_exception(logger, e, "Failed to create percentile curve")

    @stopwatch(silent=True)
    def define_histogram_curve(self, primary: str, source_data: ndarray) -> None:
        """Define the histogram plot curve.

        Args:
            * primary (str): The name of the primary data source. Only used in an Exception.
            * source_data (ndarray): The data that will be used in the curve.
        """
        try:
            plot_name: str = "Histogram"
            bins: int = int(setting(plot_name, "HistogramBinSize"))
            hist, edges = histogram(source_data, bins=bins) if bins > 1 else histogram(source_data)
            hist = divide(hist, self.file.frames())
            curve_params: dict = {
                "x": edges,
                "y": hist,
                "fillLevel": 0.0,
                "fillOutline": True,
                "stepMode": "center",
                "brush": self.brush,
            }

            if self.updatable_curve(plot_name):
                return self.curves[plot_name].setData(x=curve_params["x"], y=curve_params["y"])
            return self.define_abstract_curve(plot_name, curve_params)
        except Exception as e:
            logger.error(f"Failed to create histogram curve for {primary}")
            log_exception(logger, e, "Failed to create histogram curve")

    @stopwatch(silent=True)
    def define_box_curve(self, primary: str, source_data: ndarray) -> None:
        """Define the box plot curve.

        Because the box plot is associated with three plot types (box, error, and outliers),
        this will call for the error bars to be defined next.

        Args:
            * primary (str): The name of the primary data source. Only used in an Exception.
            * source_data (ndarray): The data that will be used in the curve.
        """
        try:
            plot_name: str = "Box"
            q1, q3 = (
                percentile(source_data, q=25),
                percentile(source_data, q=75),
            )
            curve_params: dict = {
                "x0": q1,  # Left edge
                "x1": q3,  # Right edge
                "y": 0,  # Overwritten by MainWindow.order_box_plots()
                "height": [int(setting("Box", "Height"))],
                "brush": self.brush,
            }

            if self.updatable_curve(plot_name):
                self.curves[plot_name].setOpts(
                    x0=curve_params["y0"],
                    x1=curve_params["y1"],
                    # height=curve_params["height"],
                )
            else:
                self.define_abstract_curve(plot_name, curve_params)

            # Define error bars (in which the outliers will also be defined)
            self.define_error_bars(q1, q3, source_data)
        except Exception as e:
            logger.error(f"Failed to create box plot for {primary}")
            log_exception(logger, e, "Failed to create box plot")

    @stopwatch(silent=True)
    def define_error_bars(self, q1: float, q3: float, source_data: ndarray) -> None:
        """Define the lines that will be drawn atop box plots. Called by `define_box_curve()`.

        Args:
            * primary (str): The name of the primary data source. Only used in an Exception.
            * source_data (ndarray): The data that will be used in the curve.
        """
        try:
            plot_name: str = "Error"
            iqr: float = q3 - q1
            upper_limit: float = min([max(source_data), q3 + (1.5 * iqr)])
            lower_limit: float = max([min(source_data), q1 - (1.5 * iqr)])
            positions: ndarray = array(
                [upper_limit, q3, percentile(source_data, q=50), q1, lower_limit]
            )
            curve_params: dict = {
                "x": positions,
                "y": repeat(0, 5),  # Overwritten by MainWindow.order_box_plots()
                "left": array([0, 0, 0, q1 - lower_limit, 0]),
                "right": array([0, upper_limit - q3, 0, 0, 0]),
                "height": repeat(int(setting("Box", "Height")), 5),
            }

            if self.updatable_curve(plot_name):
                self.curves[plot_name].setData(
                    x=curve_params["x"],
                    left=curve_params["left"],
                    right=curve_params["right"],
                )
            else:
                self.define_abstract_curve(plot_name, curve_params)

            # Use lower/upper limits to define outliers
            if session("ShowOutliers"):
                self.define_outliers(lower_limit, upper_limit, source_data)
        except Exception as e:
            logger.error(f"Failed to create error bars for {session('PrimaryDataSource')}")
            log_exception(logger, e, "Failed to create error bars")

    @stopwatch(silent=True)
    def define_outliers(self, lower_limit: float, upper_limit: float, source_data: ndarray) -> None:
        """Define the outlier points used with box plots. Called by `define_error_bars()`.

        Args:
            * primary (str): The name of the primary data source. Only used in an Exception.
            * source_data (ndarray): The data that will be used in the curve.
        """
        try:
            plot_name: str = "Outliers"
            lower_outliers: set = set(source_data[source_data < lower_limit])
            upper_outliers: set = set(source_data[source_data > upper_limit])

            # Skip if there are no outliers
            if not (lower_outliers or upper_outliers):
                return

            outliers = []
            if setting("Box", "OutlierValues") == "Min/Max Values":
                # Finds only extremum values (if any)
                if lower_outliers and (min_outlier := min(list(lower_outliers))):
                    outliers.append(min_outlier)
                if upper_outliers and (max_outlier := max(list(upper_outliers))):
                    outliers.append(max_outlier)
                if not outliers:
                    return
            else:
                outliers = list(lower_outliers.union(upper_outliers))

            curve_params: dict = {
                "x": outliers,
                "y": repeat(0, len(outliers)),  # Overwritten by MainWindow.order_box_plots()
                "symbol": "o",
                "symbolBrush": self.brush,
                "symbolPen": self.pen,
                "symbolSize": 5,
                "pxMode": True,
            }

            if self.updatable_curve(plot_name):
                return self.curves[plot_name].setData(x=curve_params["x"])
            return self.define_abstract_curve(plot_name, curve_params)
        except Exception as e:
            logger.error(f"Failed to create outlier points for {session('PrimaryDataSource')}")
            log_exception(logger, e, "Failed to create outlier points")

    @stopwatch(silent=True)
    def define_scatter_curve(
        self, primary: str, y_axis: ndarray, secondary: str, x_axis: ndarray
    ) -> None:
        """Define the scatter plot curve. VERY resource intensive. Only unique values will be shown.

        Args:
            * primary (str): The name of the x axis data source. Only used in an Exception.
            * y_axis (ndarray): The x axis data that will be used in the curve.
            * secondary (str): The name of the y axis data source. Only used in an Exception.
            * x_axis (ndarray): The y axis data that will be used in the curve.
        """
        try:
            plot_name: str = "Scatter"
            curve_params: dict = {
                "symbol": "o",
                "symbolBrush": self.brush,
                "symbolPen": self.pen,
                "symbolSize": 5,
                "pxMode": True,
            }

            # Deduplicate points to improve performance
            merged: ndarray = array((x_axis, y_axis)).T
            scatter_data: ndarray

            try:
                scatter_data = unique(merged, axis=0)
            except Exception:
                logger.error(f"Failed to deduplicate scatter plot data for {primary}/{secondary}")
                scatter_data = merged

            # R-squared values
            try:
                with errstate(invalid="ignore"):
                    coefficient: float = corrcoef(x_axis, y_axis)[0, 1]
                    self.r_squared = (
                        " (r=N/A)" if isnan(coefficient) else f" (r={coefficient ** 2:.3f})"
                    )
            except Exception:
                self.r_squared = " (r=N/A)"

            curve_params |= {
                "x": scatter_data[:, 0],
                "y": scatter_data[:, 1],
            }

            if self.updatable_curve(plot_name):
                return self.curves[plot_name].setData(x=curve_params["x"], y=curve_params["y"])
            return self.define_abstract_curve(plot_name, curve_params)
        except Exception as e:
            logger.error(f"Failed to create XY scatter curve for {primary}/{secondary}")
            log_exception(logger, e, "Failed to create scatter curve")

    @stopwatch(silent=True)
    def define_experience_curve(self) -> None:
        """Define the gameplay experience plot curve.

        This is exclusive to FrameView v1.1+ capture files and uses static data sources (ms/latency).
        """
        if self.file.app_name != "FrameView" or not self.file.alias_present("System Latency"):
            return

        try:
            latency: float = float(-self.get_stat("Average System\nLatency (ms)"))
            avg_fps: float = float(self.get_stat("Average FPS"))
            low_fps: float = float(self.get_stat("1% Low FPS"))

            plot_name: str = "Experience"
            curve_params: dict = {
                "x0": [latency, latency],
                "x1": [low_fps, avg_fps],
                "y": 0,  # Overwritten by MainWindow.order_experience_plots()
                "height": int(setting("Experience", "Height")),
                "brush": self.brush,
            }

            if self.updatable_curve(plot_name):
                return self.curves[plot_name].setOpts(
                    x0=curve_params["x0"],
                    x1=curve_params["x1"],
                    # height=curve_params["height"],
                )
            return self.define_abstract_curve(plot_name, curve_params)
        except Exception as e:
            logger.error(f"Failed to create gameplay experience plot for {self.file.name}")
            log_exception(logger, e, "Failed to create experience plot")
