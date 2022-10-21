"""This module is responsible for handling NVIDIA LDAT latency data files."""

from core.logger import get_logger, log_exception
from core.stopwatch import stopwatch
from numpy import float32, ndarray
from pandas import DataFrame, read_csv

from formats.capturefile import CaptureFile
from formats.integrity import Integrity

logger = get_logger(__name__)


class LDAT(CaptureFile):
    """Class for parsing LDAT log files."""

    HEADER_ALIASES: dict[str, dict[str, str]] = {
        "1.0": {
            "System Latency": "Latency",
        },
    }

    def __init__(self, **kwargs) -> None:
        try:
            super().__init__(**kwargs)
            self.integrity = Integrity.Pending
            self.headers = ["Latency"]
            self.height, self.data = self.parse_file()
        except Exception as e:
            log_exception(logger, e, "Failed to read LDAT file")

    def reset_time_axis(self, *args, **kwargs) -> None:
        """LDAT does not have a time series."""

    @stopwatch(silent=True)
    def read_log(self) -> DataFrame:
        """Read a log file and returns the data (as `float32`) in a DataFrame."""
        return read_csv(self.path, sep=",", engine="c", index_col=0, header=None, dtype=float32)

    @stopwatch
    def parse_file(self) -> tuple:
        """Call `read_log()` and determine if the time series is cumulative or discrete."""
        file_data: DataFrame = DataFrame()
        height: int = 0

        try:
            file_data = self.read_log()
            file_data.columns = self.headers
            height = file_data.shape[0]

            # LDAT files only have system latency data
            self.integrity = Integrity.Partial
        except Exception as e:
            log_exception(logger, e, "Error while parsing LDAT file")
        finally:
            return (height, file_data)

    def frametimes(self, *args, **kwargs) -> ndarray:
        """LDAT does not use any performance hooks."""
        return self.column()
