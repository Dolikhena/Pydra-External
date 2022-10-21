"""This module writes timestamped CSV and image files to the user-defined location."""

from csv import writer
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from gui.PyQt6.statusbar import StatusBarWithQueue

from core.configuration import setting
from core.logger import get_logger, log_exception
from core.stopwatch import stopwatch

logger = get_logger(__name__)


def timestamped_name() -> str:
    """Return the current timestamp."""
    return datetime.now().strftime("%b-%d-%Y_%H-%M-%S")


def output_location() -> Path:
    """Return the current output path. Create it if it does not yet exist."""
    output_path: Path = Path(setting("Exporting", "SavePath"))
    path_exists: bool = output_path.exists()

    # Create the path if it does not exist
    if not path_exists:
        logger.debug(f"Folder '{output_path.absolute()}' was created")
        output_path.mkdir(exist_ok=True)

    return output_path


@stopwatch
def write_image(scene_data: Any) -> None:
    """Export the pyqtgraph scene data as an image in a specific format."""
    try:
        # Fetch timestamp for file name
        target_format: str = setting("Exporting", "ImageFormat")
        target_name: str = f"{timestamped_name()}.{target_format}"

        # Use passed pyqtgraph ImageExporter's .export() method
        scene_data.export(str(output_location() / target_name))

        StatusBarWithQueue.post(f"Plot exported as: '{target_name}'")
        logger.debug(f"Image written: {target_name}")
    except Exception as e:
        log_exception(logger, e, "Failed to write image")


@stopwatch
def write_stats_file(table_data: Optional[list] = None) -> None:
    """Export tabulated text data to a comma-separated value file."""
    if table_data is None:
        return

    try:
        # Fetch timestamp for file name
        target_name: str = f"stats_{timestamped_name()}.csv"

        # Write tabulated data to file
        with open((output_location() / target_name), "w", newline="") as csv_file:
            file_writer = writer(csv_file, delimiter=",")
            file_writer.writerows(table_data)

        StatusBarWithQueue.post(f"Statistics file written to: '{target_name}'")
        logger.debug(f"File written: {target_name}")
    except Exception as e:
        log_exception(logger, e, "Failed to write file")


@stopwatch
def write_file_view(table_data: Optional[list] = None) -> None:
    """Export tabulated file view and related data to a comma-separated value file."""
    if table_data is None:
        return

    try:
        # Fetch timestamp for file name
        target_name: str = f"browser_{timestamped_name()}.csv"

        # Write tabulated data to file
        with open((output_location() / target_name), "w", newline="") as csv_file:
            file_writer = writer(csv_file, delimiter=",")
            file_writer.writerows(table_data)

        StatusBarWithQueue.post(f"File browser view written to: '{target_name}'")
        logger.debug(f"File written: {target_name}")
    except Exception as e:
        log_exception(logger, e, "Failed to write file")
