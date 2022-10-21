"""This module is responsible for handling GPU-Z capture files."""

from core.logger import get_logger, log_exception
from core.stopwatch import stopwatch
from numpy import array, float32, ndarray
from pandas import DataFrame, read_csv

from formats.capturefile import CaptureFile
from formats.integrity import Integrity

logger = get_logger(__name__)


class GPUZ(CaptureFile):
    """Base class for GPU-Z capture file types."""

    TIMESTAMP_FORMAT: str = "%Y-%m-%d %H:%M:%S"
    HEADER_ALIASES: dict[str, dict[str, str]] = {
        "2.0": {
            "Elapsed Time": "Time",
            "GPU Board Power": "Board Power Draw [W]",
            "GPU Chip Power": "GPU Chip Power Draw [W]",
            "GPU Frequency": "GPU Clock [MHz]",
            "GPU Temperature": "GPU Temperature [°C]",
            "GPU Utilization": "GPU Load [%]",
            "GPU Voltage": "GPU Voltage [V]",
            "CPU Temperature": "CPU Temperature [°C]",
        },
    }

    def __init__(self, **kwargs) -> None:
        try:
            super().__init__(**kwargs)
            self.integrity = Integrity.Pending
            self.data, self.headers, self.height = self.parse_file()

            # GPU-Z does not offer any kind of perf monitoring
            self.integrity = Integrity.Partial
        except Exception as e:
            log_exception(logger, e, "Failed to read GPU-Z file")

    @stopwatch(silent=True)
    def read_log(self) -> DataFrame:
        """Read a log file and returns the data in a DataFrame.

        Args:
            * file (CaptureFile): Capture file object, passed with access to instance variables.

        Returns:
            * DataFrame: Returns the file's full data block.
        """
        return read_csv(self.path, engine="python", sep=r"\s*,\s*", encoding="unicode_escape")

    @stopwatch(silent=True)
    def parse_file(self) -> tuple:
        """Call `read_log()` to obtain the log's actual data, then infer polling rate.

        Elapsed time is written to a new column using the inferred polling rate.

        Limitations:
            * Appended logs are not supported.
            * Appended logs with varying tracked headers will throw an error.

        Returns:
            * tuple: File data and number of rows.
        """
        file_data: DataFrame = DataFrame()
        headers: list[str] = []
        height: int = 0

        try:
            file_data = self.read_log()
            height = file_data.shape[0]
            polling_rate = super().infer_polling_rate(file_data["Date"])

            # Reduce dataframe memory usage by downcasting to more efficient data types
            file_data = self.compress_dataframe(file_data)

            # Write new time data to prevent precision errors from compression
            file_data["Time"] = array(file_data.index * polling_rate, dtype=float32)
            headers = file_data.columns.values.tolist()
        except Exception as e:
            log_exception(logger, e, "Error while parsing GPU-Z file")
        finally:
            return (file_data, headers, height)

    def frametimes(self, *args, **kwargs) -> ndarray:
        """GPU-Z does not use any performance hooks."""
        return self.column()
