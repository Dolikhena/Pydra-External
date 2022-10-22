"""Base class for RivaTuner-based capture file types."""

from core.logger import get_logger, log_exception
from core.stopwatch import stopwatch
from formats.integrity import Integrity
from numpy import any, array, float32, isinf, nan_to_num
from pandas import DataFrame, Series, read_csv

from formats.capturefile import CaptureFile

logger = get_logger(__name__)


class RivaTuner(CaptureFile):
    """Base class for RivaTuner-based capture file types."""

    TIMESTAMP_FORMAT: str = "%d-%m-%Y %H:%M:%S"
    # HEADER_ALIASES is defined in child modules

    def __init__(self, **kwargs) -> None:
        try:
            super().__init__(**kwargs)
            self.integrity = Integrity.Pending
            self.data, self.height = self.parse_file()
        except Exception as e:
            log_exception(logger, e, "Failed to read RivaTuner file")

    @stopwatch(silent=True)
    def read_log(self) -> DataFrame:
        """Read a log file and returns the data in a DataFrame.

        This function is shared between the MSI Afterburner and EVGA Precision X formats. MSI
        Afterburner logs have extra space between the head of the file and the actual data that is
        determined by the number of tracked metrics. This space contains some min-max data in
        addition to symbols (e.g., degrees) and suffixes (e.g., MHz) associated with the metric.

        EVGA Precision X logs (as of v1.0) have a fixed amount of rows (3) between the top of the
        file and the actual data.

        Args:
            * file (CaptureFile): Capture file object, passed with access to instance variables.

        Returns:
            * Union[DataFrame, int]: Returns the file's full data block and number of rows therein.
        """
        header_space: int = len(self.headers) + 1 if self.app_name == "MSI Afterburner" else 3
        return read_csv(
            self.path,
            engine="python",
            sep=r"\s*,\s*",
            header=None,
            skiprows=header_space,
            encoding="unicode_escape",
        )

    def extract_headers(self) -> list[str]:
        """Get headers from header block, replacing the first two headers for consistency."""
        return ["Index", "Time"] + list(
            read_csv(
                self.path,
                engine="python",
                sep=r"\s*,\s*",
                nrows=1,
                skiprows=2,
                encoding="unicode_escape",
            )
        )[2:]

    @stopwatch(silent=True)
    def parse_file(self) -> tuple:
        """Call `read_csv()` to obtain the log's actual data, then infer polling rate.

        This function is shared between the MSI Afterburner and EVGA Precision X formats. The
        timestamp column is overwritten with elapsed time using the inferred polling rate. These
        formats can sometimes benefit from compression, depending on the number of tracked metrics,
        polling rate, and total capture length.

        Limitations:
            * Appended logs are not supported.
            * Appended logs with varying tracked headers will throw an error.
            * Logs with multiple polling rates will not be interpreted accurately

        Args:
            * file (CaptureFile): Capture file object, passed with access to instance variables.

        Returns:
            * Union[DataFrame, int]: Returns the file's full data block and number of rows therein.
        """
        file_data: DataFrame = DataFrame()
        height: int = 0

        try:
            self.headers = self.extract_headers()
            if "Frametime" in self.headers or "Framerate" in self.headers:
                self.integrity = Integrity.Ideal
            else:
                self.integrity = Integrity.Partial

            file_data = self.read_log()
            file_data.columns = self.headers
            file_data = file_data.drop(columns=["Index"])
            height = file_data.shape[0]
            polling_rate = super().infer_polling_rate(file_data["Time"])

            # Reduce dataframe memory usage by downcasting to more efficient data types
            file_data = self.compress_dataframe(file_data)

            # Write new time data to prevent precision errors from compression
            file_data["Time"] = array(file_data.index * polling_rate, dtype=float32)
        except Exception as e:
            log_exception(logger, e, "Error while parsing RivaTuner file")
        finally:
            return (file_data, height)

    def frametimes(self, fps: bool = False) -> Series:
        """Return the performance series of the log.

        Args:
            * fps (bool, optional): Express performance in frames per second. This is less accurate
            for representing performance but is easier for general understanding of trends. Defaults
            to False.

        Returns:
            * ndarray: Series of frame times or frame rates for the capture.
        """
        if "Frametime" in self.headers:
            frametimes = self.column("Frametime")
            perf = 1000 / frametimes if fps else frametimes
        elif "Framerate" in self.headers:
            framerates = self.column("Framerate")
            perf = framerates if fps else 1000 / framerates
        else:
            return self.column()

        # Return zero-filled colums for fully inf columns
        if any(isinf(perf)):
            return nan_to_num(perf.to_numpy(), nan=0, posinf=0, neginf=0)
        return perf

    def tainted_frametimes(self) -> bool:
        """Return a bool indicating whether the capture has valid performance data."""
        has_fps: bool = self.alias_present("Frametimes") or self.alias_present("Framerate")
        return super().tainted_frametimes() if has_fps else True
