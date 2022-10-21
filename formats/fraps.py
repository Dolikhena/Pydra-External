"""This module is responsible for handling FRAPS capture files."""

from itertools import accumulate

from core.logger import get_logger, log_exception
from core.stopwatch import stopwatch
from formats.integrity import Integrity
from numpy import array, float32, ndarray
from pandas import DataFrame, read_csv
from pandas.core.series import Series

from formats.capturefile import CaptureFile

logger = get_logger(__name__)


class FRAPS(CaptureFile):
    """Class for parsing FRAPS and FRAPS-like log files."""

    HEADER_ALIASES: dict[str, dict[str, str]] = {
        "3.5.99": {
            "Elapsed Time": "Time (ms)",
            "Frametimes": "Frametimes",
        },
    }

    def __init__(self, **kwargs) -> None:
        try:
            super().__init__(**kwargs)
            self.integrity = Integrity.Pending
            self.headers = ["Time (ms)", "Frametimes"]
            self.height, self.data = self.parse_file()
        except Exception as e:
            log_exception(logger, e, "Failed to read FRAPS file")

    @stopwatch(silent=True)
    def read_log(self) -> DataFrame:
        """Read a log file and returns the data (as `float32`) in a DataFrame."""
        return read_csv(self.path, sep=",", engine="c", index_col=0, dtype=float32)

    @stopwatch(silent=True)
    def parse_file(self) -> tuple:
        """Call `read_log()` and determine if the time series is cumulative or discrete."""
        data: DataFrame = DataFrame()
        height: int = 0
        frames: Series = Series(dtype=float32)
        time: float = 0.0

        try:
            file_data: DataFrame = self.read_log()
            self.integrity = Integrity.Ideal
            height = file_data.shape[0]
            frames = file_data["Time (ms)"].values

            # Slice the capture into 5 equal segments and calculate each slope. If all slopes are
            # greater than 0.1, assume the frame times are expressed cumulatively. Otherwise, we
            # assume frame times are reported as discrete measurements.
            segments: int = 5
            step: float = height // segments

            # Calculate the slope ((y2 - y1) / (x2 - x1)) for each segment, check if >0.1
            slopes: ndarray = array(
                [
                    ((frames[(x * step + step - 1)] - frames[(x * step)]) / (step - 1)) > 0.1
                    for x in range(segments)
                ]
            )
            cumulative: bool = all(slopes)
            logger.debug(f"Cumulative measurements: {cumulative} ({slopes})")

            # Convert to discrete measurements
            if cumulative:
                time = frames[:-1] / 1000
                frames = array([next - cur for cur, next in zip(frames, frames[1:])])
                height = len(frames)
            else:
                time = array(list(accumulate(frames[:-1], initial=0))) / 1000

            data["Frametimes"] = frames
            data["Time (ms)"] = time
        except Exception as e:
            log_exception(logger, e, "Error while parsing FRAPS file")
        finally:
            return (height, data)
