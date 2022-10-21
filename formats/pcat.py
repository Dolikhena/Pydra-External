"""This module is responsible for handling NVIDIA PCAT capture files."""

from core.exceptions import FileIntegrityError
from core.logger import get_logger, log_exception
from core.stopwatch import stopwatch
from numpy import ndarray
from pandas import DataFrame, read_csv

from formats.capturefile import CaptureFile
from formats.integrity import Integrity

logger = get_logger(__name__)


class PCAT(CaptureFile):
    """Base class for PCAT capture file types."""

    HEADER_ALIASES: dict[str, dict[str, str]] = {
        "Release": {
            "Elapsed Time": "timestamp",
            "GPU Board Power": "w_total",
        },
    }

    def __init__(self, **kwargs) -> None:
        try:
            super().__init__(**kwargs)
            self.integrity = Integrity.Pending
            self._skip_compression = self.header_by_alias("Elapsed Time")
            self.data, self.headers, self.height = self.parse_file()

            # PCAT does not offer any kind of perf monitoring
            self.integrity = Integrity.Partial
        except Exception as e:
            log_exception(logger, e, "Failed to read PCAT file")

    @stopwatch(silent=True)
    def read_log(self) -> DataFrame:
        """Read a log file and returns the data in a DataFrame."""
        data = read_csv(self.path, sep=",", engine="c")
        return self.compress_dataframe(data)

    @stopwatch
    def parse_file(self) -> tuple:
        """Process the file's data and properties.

        Calls `read_log()`, performs compression on the returned DataFrame, zeroes the time
        domain (as PresentMon uses system uptime as basis for elapsed time), and returns headers
        along with the file data.

        Raises:
            * FileIntegrityError: Raised when a capture file is not valid.

        Returns:
            * tuple: File data, headers, and number of rows.
        """
        file_data: DataFrame = DataFrame()
        headers: list[str] = []
        height: int = 0

        try:
            file_data = self.read_log()

            if self.integrity is Integrity.Invalid:
                raise FileIntegrityError("File is invalid")

            headers = file_data.columns.values.tolist()
            height = file_data.shape[0]
        except Exception as e:
            log_exception(logger, e, "Error while parsing PCAT file")
        finally:
            return (file_data, headers, height)

    def frametimes(self, *args, **kwargs) -> ndarray:
        """PCAT does not use any performance hooks."""
        return self.column()
