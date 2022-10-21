"""Concrete factory that takes a file path and determines the original capture application."""

from os.path import commonpath
from pathlib import Path
from threading import get_native_id
from typing import Any, Callable, Optional

from pandas import read_csv

from core.exceptions import IrregularStructureError
from core.formats import Format, capture_fingerprints
from core.logger import get_logger, log_chapter, log_exception, log_table
from core.utilities import size_from_bytes
from formats.verbatim import Verbatim

logger = get_logger(__name__)


class FileLoader:
    """An adapter for capture file parser modules.

    This will attempt to identify what application created a log file (e.g., FrameView, PCAT,
    HWiNFO, etc.) and, if it can find match the log's headers versus known headers, will create
    a concrete product for that capture type.

    Returns:
        * CaptureFile-subclassed object appropriate for the capture type.
    """

    _thread_ids: dict[str, list] = {}

    @classmethod
    def associate_thread(cls, thread_id: int, file_name: str) -> None:
        """Track the assigned thread ID for the worker that processed a file."""
        id_to_str = str(thread_id)
        if file_name not in cls._thread_ids:
            cls._thread_ids[file_name] = [id_to_str]
        else:
            cls._thread_ids[file_name] += [id_to_str]

    @classmethod
    def report_thread_associations(cls) -> None:
        """Report file-thread associations at the end of the session."""
        if cls._thread_ids:
            file_names: list[str] = list(cls._thread_ids.keys())
            common: str = ""

            try:
                if len(file_names) > 1:
                    common = commonpath(file_names)
                    logger.debug(f"Common path prefix: {common}")
            except ValueError:
                # Raised when file paths aren't from the same drive
                common = ""

            split_dict = {k.removeprefix(common): ", ".join(v) for k, v in cls._thread_ids.items()}
            log_table(logger, split_dict, headers=("File Name", "Thread ID"))

    __slots__ = ("file_name", "file_path", "callback")

    def __init__(self, file_path: Path, callback: Optional[Callable]) -> None:
        """Create a new FileLoader object from the provided file path.

        Args:
            * file_path (Path): Absolute resource path.
            * callback (Callable): Function that is connected to a Qt slot.
        """
        self.file_name: str = file_path.name
        self.file_path: Path = file_path
        self.callback: Optional[Callable] = callback

        log_chapter(logger, f"Loading file: {self.file_name}")
        FileLoader.associate_thread(get_native_id(), str(file_path))

    def read_line(self, **kwargs) -> list:
        """Read a single row of a capture file to obtain its headers."""
        return read_csv(self.file_path, nrows=1, **kwargs).columns.values.tolist()

    def find_headers(self) -> list:
        """Use results from `read_headers()` to better identify which app produced the log.

        Raises:
            * IrregularStructureError: Raised when encountering files that have an inconsistent
            width, including but not limited to MSI Afterburner and EVGA Precision X logs.

        Returns:
            * list: File headers, used to match the application type.
        """
        headers: list = []
        try:
            headers = self.read_line(sep=",", engine="c", encoding="unicode_escape")

            # Check for known headers in Afterburner/Precision logs
            if headers[0] == "00" and "Hardware monitoring log" in headers[2]:
                raise IrregularStructureError("File has an irregular structure")
        except DeprecationWarning:
            headers = self.read_line(sep=",", engine="c")
        except UnicodeDecodeError:
            logger.info("File contains utf-8 characters, reattempting with unicode escape")
            headers = self.read_line(sep=",", engine="c", encoding="unicode_escape")
        except IrregularStructureError:
            logger.info("Reattempting to read as fixed-width file")
            # These are essentially fixed-width files delimited by whitespace-comma-whitespace
            headers = self.read_line(
                engine="python", sep=r"\s*,\s*", skiprows=2, encoding="unicode_escape"
            )
        except Exception as e:
            log_exception(logger, e, "Failed to interpret file")
        finally:
            return headers

    def verbatim_file(self) -> Verbatim:
        """Create a verbatim object with minimum viable parameters."""
        return Verbatim(name=self.file_name, path=self.file_path, callback=self.callback)

    def infer_format(self) -> Any:
        """Obtain headers from `find_headers()` and tests against archetypical file headers.

        Returns:
            * Callable: An appropriate object instance for a capture format, or nothing if it
            cannot find a match.
        """
        headers: list[str] = [h.strip() for h in self.find_headers()]
        verbatim: Callable = self.verbatim_file

        # Return verbatim file if there was error processing headers
        if headers is None:
            return verbatim()

        header_set: set[str] = set(headers)
        application: Optional[Format] = None
        version: Optional[str] = None
        percent_matches: float = 0.0

        # Compare file headers to format header archetypes and select the best fit
        for app, versions in capture_fingerprints.items():
            for ver, match_set in versions.items():
                shared_headers = len(header_set.intersection(match_set)) / len(match_set)
                if shared_headers > 0 and shared_headers >= percent_matches:
                    application, version, percent_matches = app, ver, shared_headers

        # Return verbatim file if the capture type couldn't be determined
        if application is None:
            logger.info(f"{self.file_name} does not have an associated handler")
            logger.info(f"Detected headers: {headers}")
            return verbatim()

        logger.debug(f"Size on disk: {(size_from_bytes(self.file_path.stat().st_size))}")
        logger.debug(f"Capture type: {application.app_name()} {version}")
        logger.debug(f"Fingerprint match: {percent_matches:.0%}")

        try:
            return application.parser(
                app_name=application.app_name(),
                version=version,
                name=self.file_name,
                path=self.file_path,
                headers=headers,
                callback=self.callback,
            )
        except RuntimeError:
            logger.error(f"{application.app_name()} object was destroyed unexpectedly")
            return None
        except Exception as e:
            log_exception(logger, e)
            return verbatim()
