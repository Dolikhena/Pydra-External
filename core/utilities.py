"""Collection of common functions used by multiple Pydra modules."""

from enum import Enum
from typing import Any, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QColorDialog

from core.configuration import setting
from core.logger import get_logger
from core.stopwatch import stopwatch

logger = get_logger(__name__)


class Tab(Enum):
    """Indices for tab views in the main menu."""

    Line = 0
    Percentiles = 1
    Histogram = 2
    Box = 3
    Scatter = 4
    Experience = 5
    Statistics = 6
    FileBrowser = 7
    Log = 8


class Column(Enum):
    """Verbose labels for statistics column properties, like which are mutable or comparable."""

    Static = 0
    Mutable = 1
    Comparable = 2


time_scales: dict[str, tuple] = {
    "Seconds": ("(s)", "(sec)", 1),
    "Minutes": ("(m)", "(min)", 60),
    "Hours": ("(h)", "(hr)", 3600),
    # "Days": ("(d)", "(day)", 86400),
}


def time_str_short() -> int:
    """Return the time scale multiplier."""
    return time_scales[setting("General", "TimeScale")][0]


def time_str_long() -> int:
    """Return the time scale multiplier."""
    return time_scales[setting("General", "TimeScale")][1]


def time_scale() -> int:
    """Return the time scale multiplier."""
    return time_scales[setting("General", "TimeScale")][2]


@stopwatch(silent=True)
def stat_table_headers() -> dict[str, tuple]:
    """Return a dictionary containing headers and cell alignments for the statistics table.

    The order of the table headers is determined by the order of these key-value pairs.

    Any modifications to the column headers MUST be copied in the MainWindow instance
    variable in gui.dialogs.stat_metrics as well as the categorical methods in PlotObject.
    """
    align_left = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    align_center = Qt.AlignmentFlag.AlignCenter
    time_str = time_str_short()

    return {
        # Capture metadata
        "Capture\nType": (align_left, Column.Static),
        "Capture\nIntegrity": (align_center, Column.Static),
        "Application": (align_center, Column.Mutable),
        "Resolution": (align_center, Column.Mutable),
        "Runtime": (align_center, Column.Mutable),
        "GPU": (align_center, Column.Mutable),
        "Comments": (align_center, Column.Mutable),
        # Performance metrics
        f"Duration {time_str}": (align_center, Column.Static),
        "Number\nof Frames": (align_center, Column.Comparable),
        "Synced\nFrames": (align_center, Column.Comparable),
        # Frame rate
        "Minimum FPS": (align_center, Column.Comparable),
        "Average FPS": (align_center, Column.Comparable),
        "Median FPS": (align_center, Column.Comparable),
        "Maximum FPS": (align_center, Column.Comparable),
        # Frame rate percentiles
        "0.1% Low FPS": (align_center, Column.Comparable),
        "0.1% FPS": (align_center, Column.Comparable),
        "1% Low FPS": (align_center, Column.Comparable),
        "1% FPS": (align_center, Column.Comparable),
        "5% FPS": (align_center, Column.Comparable),
        "10% FPS": (align_center, Column.Comparable),
        # Relative fps metrics
        "0.1% Low FPS\n/ Average FPS": (align_center, Column.Comparable),
        "0.1% FPS\n/ Average FPS": (align_center, Column.Comparable),
        "1% Low FPS\n/ Average FPS": (align_center, Column.Comparable),
        "1% FPS\n/ Average FPS": (align_center, Column.Comparable),
        "5% FPS\n/ Average FPS": (align_center, Column.Comparable),
        "10% FPS\n/ Average FPS": (align_center, Column.Comparable),
        # Stutter metrics
        "Number of\nStutter Events": (align_center, Column.Comparable),
        "Proportion\nof Stutter": (align_center, Column.Comparable),
        "Average\nStutter": (align_center, Column.Comparable),
        "Maximum\nStutter": (align_center, Column.Comparable),
        # GPU metrics
        "Average System\nLatency (ms)": (align_center, Column.Comparable),
        "Average Perf-\nper-Watt (F/J)": (align_center, Column.Comparable),
        "Average GPU\nBoard Power (W)": (align_center, Column.Comparable),
        "Average GPU\nChip Power (W)": (align_center, Column.Comparable),
        "Average GPU\nFrequency (MHz)": (align_center, Column.Comparable),
        "Average GPU\nTemperature (°C)": (align_center, Column.Comparable),
        "Average GPU\nUtilization (%)": (align_center, Column.Comparable),
        "Average GPU\nVoltage (V)": (align_center, Column.Comparable),
        # CPU metrics
        "Average CPU\nPower (W)": (align_center, Column.Comparable),
        "Average CPU\nFrequency (MHz)": (align_center, Column.Comparable),
        "Average CPU\nTemperature (°C)": (align_center, Column.Comparable),
        "Average CPU\nUtilization (%)": (align_center, Column.Comparable),
        # Battery metrics
        "Average Battery\nCharge Rate (W)": (align_center, Column.Comparable),
        f"Projected\nBattery Life {time_str}": (align_center, Column.Comparable),
        # Capture metadata (continued)
        "File Name": (align_left, Column.Static),
        "File Location": (align_left, Column.Static),
    }


# Can be defined at init since these headers won't change during runtime
mutable_headers: list[str] = [k for k, v in stat_table_headers().items() if v[1] is Column.Mutable]


def mutable_table_headers() -> list[str]:
    """Return a tuple of the statistics table columns that users are allowed to edit."""
    return mutable_headers


def numeric_table_headers() -> list[str]:
    """Return a tuple of the statistics table columns that users are allowed to edit."""
    return [k for k, v in stat_table_headers().items() if v[1] is Column.Comparable]


def table_indices() -> Any:
    """Return the index list of each header, used to match data to the appropriate column."""
    return list(stat_table_headers()).index


def preserve_marks(previous_value: str, new_value: str) -> str:
    """Prevent asterisks from being stripped from or added to a string.

    Args:
        * previous_value (str): Original cell value.
        * new_value (str): Modified cell value.

    Returns:
        * str: Modified cell value that honors file integrity, with surrounding whitespace removed.
    """
    previous_value = previous_value.strip()
    new_value = new_value.strip()

    if not new_value.replace("*", ""):
        return previous_value

    marked_previous_value: bool = previous_value.endswith("*")
    marked_new_value: bool = new_value.endswith("*")

    # Don't allow asterisks to be removed
    if marked_previous_value and not marked_new_value:
        new_value = f"{new_value}*"
    elif not marked_previous_value and marked_new_value:
        while new_value.endswith("*"):
            new_value = new_value.removesuffix("*")

    return new_value


def size_from_bytes(object_size: float) -> str:
    """Convert an object size (in bytes) to a more sensible representation.

    Returns:
        * str: Human-readable object size and size format. (example: "132.5 MB")
    """
    if object_size < 1000:
        unit = "bytes"
    elif object_size < 1_000_000:
        object_size /= 1000
        unit = "KB"
    elif object_size < 1_000_000_000:
        object_size /= 1_000_000
        unit = "MB"
    else:
        object_size /= 1_000_000_000
        unit = "GB"

    return f"{object_size:,.1f} {unit}"


def color_picker(default_color=QColor(255, 255, 255)) -> Optional[tuple[int, int, int]]:
    """Raise a color picker dialog window for selecting a new color."""
    if isinstance(default_color, tuple):
        default_color = QColor(*default_color)

    color_picker_dialog = QColorDialog().getColor(initial=default_color)
    if QColor.isValid(color_picker_dialog):
        return (
            color_picker_dialog.red(),
            color_picker_dialog.green(),
            color_picker_dialog.blue(),
        )
    return None


def vendor_gpu_substrings() -> dict[str, tuple]:
    """Attempt to identify a GPU's manufacturer according to the presence of key words."""
    return {
        "NVIDIA": ("NVIDIA", "GEFORCE", "RTX", "GTX", "TITAN", "QUADRO"),
        "AMD": ("AMD", "RADEON", "RX", "VEGA", "VII"),
        "INTEL": (
            "ARC",
            "INTEL",
            "IRIS",
            "UHD GRAPHICS",
            "HD GRAPHICS",
        ),
    }


def default_data_sources() -> tuple[str]:
    """Return the standard (categorical) data sources."""
    return (
        "Frame Time (ms)",
        "Frame Rate (fps)",
        "Interframe Variation (ms)",
        "Stutter (%)",
        "Total Board Power (W)",
        "Graphics Chip Power (W)",
        "Perf-per-Watt (F/J)",
        "System Latency (ms)",
        "GPU Frequency (MHz)",
        "GPU Temperature (°C)",
        "GPU Utilization (%)",
        "GPU Voltage (V)",
        "CPU Power (W)",
        "CPU Frequency (MHz)",
        "CPU Temperature (°C)",
        "CPU Utilization (%)",
        "Battery Charge Rate (W)",
        "Battery Level (%)",
    )
