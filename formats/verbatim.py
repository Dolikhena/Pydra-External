"""This module is responsible for reading comma-separated files that otherwise lack support."""

from core.logger import get_logger, log_exception
from core.stopwatch import stopwatch
from numpy import max
from pandas import DataFrame, read_csv, to_numeric
from pandas.errors import ParserError

from formats.capturefile import CaptureFile
from formats.integrity import Integrity

logger = get_logger(__name__)


class Verbatim(CaptureFile):
    """Class for reading comma-separated files."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        logger.info("Reading file verbatim due to errors")

        self.data, self.headers = self.parse_file()
        self.height = self.data.shape[0]
        self.integrity = Integrity.Invalid

    @stopwatch
    def parse_file(self) -> tuple[DataFrame, list[str]]:
        """Read a CSV-like file into a DataFrame that can be viewed in the file browser.

        Returns:
            * DataFrame: File data.
        """
        data: DataFrame = DataFrame()
        headers: list[str] = []

        try:
            # Attempt reading as a coherent delimited file
            data = read_csv(self.path, sep=None, engine="python", encoding="unicode_escape")
            data = self.compress_dataframe(data)
            headers = data.columns.values.tolist()
        except ParserError:
            # Switch to line-based reading and backfill values
            logger.debug("Structured verbatim read failed, attempting line-based read")
            contents: list[str] = []
            widths: list[int] = []
            lines: list[str] = []
            row: list[str] = []

            # Build a 2D list of exact values
            with open(self.path, "r", newline=None) as file:
                lines = file.readlines()
                for line in lines:
                    row = line.strip().split(",")
                    contents.append(row)
                    widths.append(len(row))

            # Reiterate over list to fill in missing values
            max_width = max(widths)
            for row in contents:
                while len(row) < max_width:
                    row.append("<Missing>")

            # Use first content row as headers, stripping quotes
            headers = [h.replace('"', "").strip() for h in contents[0]]

            # Cast data to DataFrame using provided column names, then drop first row
            data = DataFrame(contents, columns=headers).iloc[1:]

            # Attempt casting strings to numeric datatypes
            data = self.compress_dataframe(data.apply(to_numeric, errors="ignore"))
        except Exception as e:
            log_exception(logger, e, "Verbatim read failed")
        finally:
            return data, headers

    @staticmethod
    def read_log() -> None:
        """Unused for this capture type."""

    @staticmethod
    def elapsed_time() -> None:
        """Unused for this capture type."""

    @staticmethod
    def frametimes() -> None:
        """Unused for this capture type."""

    @staticmethod
    def power() -> None:
        """Unused for this capture type."""
