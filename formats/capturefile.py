"""Abstract base class used by capture file formats."""

from abc import ABC, abstractmethod
from collections import namedtuple
from dataclasses import dataclass
from hashlib import sha3_256
from typing import Any, Callable, Optional

from core.configuration import setting, setting_bool
from core.logger import get_logger, log_chapter, log_exception
from core.signaller import TupleSignaller
from core.stopwatch import stopwatch
from core.utilities import size_from_bytes
from gui.metadata import read_record, record_exists, remove_record, update_record
from gui.PyQt6.statusbar import StatusBarWithQueue
from numpy import (
    abs,
    any,
    array,
    average,
    float32,
    int8,
    int16,
    int32,
    int64,
    isfinite,
    isinf,
    isnan,
    max,
    median,
    min,
    ndarray,
    round,
    std,
    sum,
    uint8,
    uint16,
    uint32,
    where,
    zeros,
)
from pandas import DataFrame, Series, to_datetime

from formats.integrity import Integrity

logger = get_logger(__name__)

_STUTTER = namedtuple("Stutter", ["deviations", "total", "proportional", "average", "max"])


@dataclass
class InspectionItem:
    passed: bool
    # severity: Enum
    violations: int
    description: str

    @staticmethod
    def default_result() -> object:
        return InspectionItem(passed=False, violations=-1, description="Field inspection failed")


class CaptureFile(ABC):
    """Superclass for all capture parser modules."""

    _HASH_ALGORITHM = sha3_256
    _HASH_BLOCK_SIZE: int = 65536

    @classmethod
    def aliases(cls, version: str) -> dict[str, str]:
        """Return the alias list of a capture type's class."""
        return cls.HEADER_ALIASES.get(version, "None")

    @classmethod
    def timestamp(cls, version: str) -> str:
        """Return the datetime format for a capture type, which can be versioned."""
        try:
            return (
                cls.TIMESTAMP_FORMAT
                if isinstance(cls.TIMESTAMP_FORMAT, str)
                else cls.TIMESTAMP_FORMAT[version]
            )
        except Exception as e:
            log_exception(logger, e, "Timestamp lookup failed")

    __slots__ = (
        "_signaller",
        "_skip_compression",
        "app_name",
        "callback",
        "data",
        "duplicate_headers",
        "fallbacks_in_use",
        "hash",
        "headers",
        "height",
        "integrity",
        "name",
        "offset",
        "path",
        "perf_per_watt_data",
        "properties",
        "stutter_data",
        "uses_saved_properties",
        "version",
        "zero_col",
    )

    def __init__(self, **kwargs) -> None:
        self._signaller: TupleSignaller = TupleSignaller()
        self._skip_compression: Any = None
        self.app_name: str = "Unknown"
        self.callback: Callable
        self.data: Optional[DataFrame] = None
        self.duplicate_headers: Optional[list] = None
        self.fallbacks_in_use: Optional[dict] = {}
        self.headers: Optional[list] = None
        self.hash: str = ""
        self.height: int = 0
        self.integrity: Integrity
        self.name: str = ""
        self.offset: int = 0
        self.path: str = ""
        self.perf_per_watt_data: Optional[Series] = None
        self.properties: dict = {
            "Application": "Unknown",
            "Resolution": "Unknown",
            "Runtime": "Unknown",
            "GPU": "Unknown",
            "Comments": "None",
            "Legend": (False, ""),
        }
        self.stutter_data: Optional[tuple] = None
        self.uses_saved_properties: Optional[bool] = None
        self.version: str = ""
        self.zero_col: Optional[Series] = None

        # Set passed keyword args
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.path = str(self.path)
        self.hash = self.compute_file_hash()

        log_chapter(logger, f"Parsing {self.app_name} file: {self.name}")

        # Connect Qt object for emitting integrity changes (if object is valid)
        self._signaller.signal.connect(self.callback)
        self.integrity = Integrity.Initialized

    def __setattr__(self, name: str, value) -> None:
        """Emit a Qt signal when the object's 'integrity' property has been modified."""
        if name == "integrity" and hasattr(self, "integrity") and value != self.integrity:
            super().__setattr__(name, value)
            return self._signaller.signal.emit((self.path, value))
        super().__setattr__(name, value)

    def frames(self) -> int:
        """Return the current number of visible frames (rows) in a capture file."""
        return self.height - self.offset

    def valid_file_setup(self) -> None:
        """Deeper object setup, reserved for recognized and valid files."""
        self.reset_time_axis(remove_time_record=False)
        self.restore_saved_properties()
        self.find_duplicate_headers()

        # Check if file's performance data is incompatible with stutter heuristics
        if self.tainted_frametimes() and self.integrity == Integrity.Ideal:
            self.integrity = Integrity.Dirty

    @staticmethod
    def calculate_file_hash(file_blocks) -> str:
        """Create a hash digest for the file."""
        algorithm = CaptureFile._HASH_ALGORITHM()
        for block in file_blocks:
            algorithm.update(block)
        return str(algorithm.hexdigest())

    def iterable_file_blocks(self) -> bytes:
        """Split file's binary data into iterable, uniformly-sized blocks."""
        with open(self.path, "rb") as file:
            block = file.read(CaptureFile._HASH_BLOCK_SIZE)

            while len(block) > 0:
                yield block
                block = file.read(CaptureFile._HASH_BLOCK_SIZE)

    @stopwatch(silent=True)
    def compute_file_hash(self) -> str:
        """Fetch a file's hash, useful for matching files across systems and directories."""
        return self.calculate_file_hash(self.iterable_file_blocks())

    @staticmethod
    @abstractmethod
    def read_log() -> None:
        """Read a log file and returns the data in a DataFrame."""

    @staticmethod
    @abstractmethod
    def parse_file() -> None:
        """Process the file's data and properties."""

    @stopwatch(silent=True)
    def downcast_col(self, col: Series) -> Series:
        """Downcast a Pandas Series to a more memory-efficient data type."""
        col_name: str = str(col.name)
        if self._skip_compression is not None and col_name in self._skip_compression:
            return col

        original_size: int = col.memory_usage()
        _column = array(col)  # For initial downcasting
        _type = self.return_optimal_dtype(_column)

        # Recast column based on heuristics
        if _type is None:
            logger.error(f"Couldn't find a suitable numeric dtype for '{col_name}'")
            return col
        _column = col.astype(_type)

        # Don't return a less memory-efficient column
        if original_size < _column.nbytes:
            logger.error(f"Column '{col_name}' does not benefit from downcasting")
            return col

        return Series(_column)

    @staticmethod
    @stopwatch(silent=True)
    def return_optimal_dtype(data: Series) -> Any:
        """Return the most efficient numeric dtype for a Pandas Series."""
        if data.dtype == object:
            return "category"  # Fallback, compresses strings

        _first = data[0]
        _min = min(data)
        _max = max(data)

        # Cast as integer or float
        if (_first - _first.astype(int64)) == 0:
            # Unsigned int
            if _min >= 0:
                if _max < 256:
                    _type = uint8
                elif _max < 65_536:
                    _type = uint16
                elif _max < 4_294_967_296:
                    _type = uint32
                # elif _mx < 18_446_744_073_709_551_616:
                #     _type = uint64
            # Signed int
            elif _min > -129 or _max < 128:
                _type = int8
            elif _min > -32_769 or _max < 32_768:
                _type = int16
            elif _min > -2_147_483_649 or _max < 2_147_483_648:
                _type = int32
            # elif _mn > -9_223_372_036_854_775_809 or _mx < 9_223_372_036_854_775_808:
            #     _type = int64
            else:
                return None
        else:
            _type = float32  # fp16 isn't any faster and fp64 is unnecessary
        return _type

    @stopwatch
    def compress_dataframe(self, data: DataFrame) -> DataFrame:
        """Optimize a full-fat DataFrame by dropping fully NA columns and downcasting dtypes.

        Downcasting will only be applied to DataFrames whose size exceeds `CompressionMinSizeMB`,
        and similarly, only fully NA columns will be dropped if `DropNAColumns` is True.
        """
        # Skips and suppresses warnings from empty DataFrames
        if data.empty:
            return data

        # Config settings
        compression_min_size: int = int(setting("General", "CompressionMinSizeMB"))
        drop_na_columns: bool = setting_bool("General", "DropNAColumns")

        initial_malloc: int = sum(data.memory_usage(deep=True))
        checkpoint_malloc: int
        compressed_malloc: int

        # Report dimensions and memory usage of original DataFrame
        height, width = data.shape
        logger.debug(
            f"Original dimensions: {width} x {height:,} ({width * height:,} elements), "
            f"{size_from_bytes(initial_malloc)} in RAM"
        )

        # Drop fully NA columns if desired by user. This can further reduce memory usage for very wide
        # capture files with unused fields (e.g., FrameView, HWiNFO).
        if drop_na_columns:
            data.dropna(axis="columns", how="all", inplace=True)
            reduced_width: int = data.shape[1]
            checkpoint_malloc = sum(data.memory_usage(deep=True))

            if (num_dropped := width - reduced_width) > 0:
                # Record the number of dropped columns
                logger.debug(f"Dropped {num_dropped} NA column{'s' if num_dropped != 1 else ''}")

                # Report the updated dimensions and memory usage
                width = reduced_width
                logger.debug(
                    f"Reduced dimensions: {width} x {height:,} ({width * height:,} elements), "
                    f"{size_from_bytes(checkpoint_malloc)} in RAM (Reduced by "
                    f"{1 - (checkpoint_malloc / initial_malloc):.1%})"
                )
        else:
            checkpoint_malloc = initial_malloc

        # Test if DataFrame memory usage (NA-culled or otherwise) is beneath compression threshold
        if checkpoint_malloc < (compression_min_size * 1_048_576):
            logger.debug(
                f"DataFrame RAM usage ({size_from_bytes(checkpoint_malloc)}) is below "
                f"CompressionMinSizeMB ({compression_min_size} MB)"
            )
            return data

        # Broadcast column-wise downcasting
        data = data.apply(self.downcast_col)

        # Report reduced memory usage
        compressed_malloc = sum(data.memory_usage(deep=True))
        logger.debug(
            f"Compressed dimensions: {width} x {height:,} ({width * height:,} elements), "
            f"{size_from_bytes(compressed_malloc)} in RAM (Reduced by "
            f"{1 - (compressed_malloc / initial_malloc):.1%})"
        )

        return data

    @stopwatch(silent=True)
    def stutter_heuristic(self) -> tuple:
        """Calculate frame time stutter deltas and the percentage of stutter frames for a capture.

        We detect potential stutter issues by comparing each frame time against the median of a rolling
        window of 19 frames. Any frame that deviates from the local window by more than 20% and 4 ms is
        considered a stutter frame.

        We list the following, expressed in percentages:
        * The percentage of stutter frames out of all frames in the capture.
        * Average stutter delta of stutter frames relative to their local median frame time.
        * Max stutter delta in order to quantify the worst stutter frame encountered (for context).

        If there are more than 1% stutter frames, if average stutter delta is over 60%, or if the max
        frame-time delta is over 2x the average stutter delta, we flag a potential issue.

        Returns:
            * tuple:
                * (ndarray): Array of frame time delta percentages.
                * (int): Number of stutter frames in the capture.
                * (float): The percentage of stutter frames out of all frames.
                * (float): The average stutter amplitude.
                * (float): The maximum stutter amplitude.
        """
        frametimes: Series = Series(
            self.frametimes(), dtype=float32
        )  # Cast as pd.Series for rolling methods
        num_all_frames: int = len(frametimes)
        invalid_stutter = _STUTTER(zeros((num_all_frames,), dtype=uint8), 0.0, 0.0, 0.0, 0.0)

        try:
            # Do not run if the minimum frame time is zero or contains non-finite numbers
            if min(frametimes) == 0 or any(isinf(frametimes)):
                return invalid_stutter

            # Config settings
            test_for_osc: bool = setting_bool("OscillationHeuristic", "TestForOscillation")
            window_size: int = int(setting("StutterHeuristic", "StutterWindowSize"))

            # Compute rolling frametime windows. Used by stutter and oscillation heuristics.
            rolling_frametimes = frametimes.rolling(
                window_size, min_periods=window_size, center=True
            )

            # Determine presence of oscillating frametimes, if enabled by the user.
            if test_for_osc:
                oscillation = self.oscillation_heuristic(rolling_frametimes, num_all_frames)
                if oscillation is not None:
                    return oscillation

            # Fetch other config settings if oscillation heuristic wasn't triggered or run
            delta_ms: float = float(setting("StutterHeuristic", "StutterDeltaMs"))
            delta_pct: float = float(setting("StutterHeuristic", "StutterDeltaPct")) / 100

            # Calculate rolling median (default: 19 frames)
            rolling_median: Series = rolling_frametimes.median()

            frame_time_deviations: ndarray = abs(frametimes - rolling_median)
            percent_deviations: ndarray = array(frame_time_deviations / rolling_median)

            # Test if delta between frame time and median exceeds threshold (default: 20%)
            percent_delta: ndarray = array(percent_deviations > delta_pct)

            # Test if each frame time delta is also greater than threshold (default: 4 ms)
            ms_delta: ndarray = array(frame_time_deviations > delta_ms)

            # Consider as stutter event if the two above conditions are true
            stutter_frames: ndarray = array(percent_delta & ms_delta, dtype=uint8)
            stutter_deltas: ndarray = percent_deviations[where(stutter_frames == 1)]

            # Calculate statistics on stutter data
            num_stutter_frames: int = sum(stutter_frames)
            pct_stutter_frames: float = 0
            avg_stutter_delta: float = 0
            max_stutter_delta: float = 0

            if num_stutter_frames > 0:
                pct_stutter_frames = num_stutter_frames / num_all_frames
                avg_stutter_delta = average(stutter_deltas)
                max_stutter_delta = max(stutter_deltas)

            return _STUTTER(
                percent_deviations,
                num_stutter_frames,
                pct_stutter_frames,
                avg_stutter_delta,
                max_stutter_delta,
            )
        except Exception as e:
            log_exception(logger, e)
            return invalid_stutter

    @staticmethod
    @stopwatch(silent=True)
    def oscillation_heuristic(rolling_frames, num_frames: int) -> Optional[tuple]:
        """Pathological long-short frametime patterns are underreported with stutter heuristic.

        Args:
            * rolling_frames: Data structure containing the results of Pandas' Rolling function.
            * num_frames (int): Total number of indvidual frames in the capture.

        Returns:
            * Optional[tuple]: If a significant proportion of oscillation events are detected, returns
            a tuple matching the namedtuple returned by `stutter_heuristic` except only the number and
            overall percentage results are provided.
        """
        if num_frames == 0:
            return None

        oscillations = namedtuple(
            "oscillations", ["deviations", "total", "proportional", "average", "max"]
        )
        try:
            delta_ms: float = float(setting("OscillationHeuristic", "OscDeltaMs")) / 100
            delta_pct: float = float(setting("OscillationHeuristic", "OscDeltaPct")) / 100
            warn_pct = float(setting("OscillationHeuristic", "OscWarnPct")) / 100

            # Calculate 1st and 3rd quartile rolling windows
            rolling_q1: Series = rolling_frames.quantile(0.25)
            rolling_q3: Series = rolling_frames.quantile(0.75)

            # Test if each window's interquartile difference is greater than threshold (default: 20%)
            osc_percent_delta: Series = ((rolling_q3 / rolling_q1) - 1) >= delta_pct

            # Test if window IQR is greater than threshold (default: 4 ms)
            osc_ms_delta: Series = (rolling_q3 - rolling_q1) >= delta_ms

            # Mark window as oscillation period if the two above conditions are true
            osc_frames: ndarray = array(osc_percent_delta & osc_ms_delta, dtype=uint8)
            num_osc_frames: int = sum(osc_frames)
            pct_osc_frames: float = num_osc_frames / num_frames

            # Exit early if oscillation does not appear to be present in the capture
            if pct_osc_frames < warn_pct:
                return None

            return oscillations("OSC", num_osc_frames, pct_osc_frames, "OSC", "OSC")
        except Exception as e:
            log_exception(logger, e)
            return None

    def calculate_stutter(self) -> tuple:
        """Determine stutter/oscillation behaviors in performance series.

        'OSC' indicates excessive local oscillation in frame times and thus window metrics are unusable.

        Limitations:
            * Any zeros in performance series will prevent the calculation of stutter and oscillation.

        Todo:
            * CPU boundedness heuristic
            * Cinematic/loading screen heuristic

        Raises:
            * StutterZeroException: Raised if there are any zeros in frametime_data.

        Returns:
            * tuple:
                * (ndarray): Array of frame time delta percentages.
                * (int): Number of stutter frames in the capture.
                * (float): The percentage of stutter frames out of all frames.
                * (float): The average stutter amplitude.
                * (float): The maximum stutter amplitude.
        """
        return self.stutter_heuristic()

    def evaluate_integrity(self) -> None:
        """Evaluate a file's properties and quality, at creation or in response to alterations."""

    def resize_zero_column(self) -> None:
        self.zero_col = Series(zeros((self.frames(),), dtype=uint8))

    def find_duplicate_headers(self) -> None:
        """Count and log duplicated column headers."""
        unique_headers: list = []
        duplicates: list = []

        for header in self.headers:
            container = unique_headers if header not in unique_headers else duplicates
            container.append(header)

        if duplicates:
            logger.info(f"{self.name} contains {len(duplicates):,} duplicate headers: {duplicates}")
            self.duplicate_headers = duplicates

    def preferred_aliases(self, generic_phrase: str = "") -> str:
        return self.aliases(self.version).get(generic_phrase, "None")

    def fallback_aliases(self) -> dict[str, str]:
        """Return the alias list of a capture type's class."""
        return self.FALLBACK_HEADER_ALIASES.get(self.version, "None")

    def register_fallback_header(self, generic_phrase: str = "") -> None:
        """Register a fallback header that should be used instead of the preferred header."""
        if not hasattr(self, "FALLBACK_HEADER_ALIASES"):
            return logger.error(f"{self.name} has no fallback header structure")
        elif generic_phrase not in self.fallback_aliases():
            return logger.error(f"{self.name} has no fallback header for '{generic_phrase}'")

        fallback_header: str = self.fallback_aliases().get(generic_phrase, "None")
        logger.info(f"{self.name} will use '{fallback_header}' as fallback for '{generic_phrase}'")
        self.fallbacks_in_use[generic_phrase] = fallback_header

    def remove_fallback_header(self, generic_phrase: str = "") -> None:
        """Remove a registered fallback header."""
        if generic_phrase in self.fallbacks_in_use:
            logger.info(f"{self.name} will now use the preferred header for '{generic_phrase}'")
            return self.fallbacks_in_use.pop(generic_phrase)

    def header_by_alias(self, generic_phrase: str) -> str:
        """Accept a generic string (e.g., "Frametimes") and provides a version-specific header.

        This prioritizes using fallback headers, if they are defined. If a header-phrase pair is
        undefined for a capture type/version, this returns None.
        """
        # if generic_phrase in self.fallbacks_in_use:
        #     return self.fallbacks_in_use.get(generic_phrase, "None")
        # preferred_header: str = self.aliases(self.version).get(generic_phrase, "None")
        # if preferred_header in self.headers:
        #     return preferred_header
        # Automatically register fallbacks for missing headers - could be unsafe
        # elif generic_phrase in self.fallback_aliases():
        #     self.register_fallback_header(generic_phrase)
        #     return self.fallbacks_in_use.get(generic_phrase, "None")
        # return "None"
        return self.fallbacks_in_use.get(generic_phrase, self.preferred_aliases(generic_phrase))

    def alias_in_headers(self, column_name: str) -> bool:
        """Return a bool indicating if a header alias exists for a file."""
        return self.header_by_alias(column_name) in self.headers

    def alias_present(self, generic_phrase: str) -> bool:
        """Return a bool indicating if a file contains an aliased header."""
        translation: str = self.header_by_alias(generic_phrase)
        return translation in self.headers and translation != "None"

    def define_properties(self) -> None:
        """Detect and report capture metadata for use in the stat table."""
        self.properties = {
            "Application": "Unknown",
            "Resolution": "Unknown",
            "Runtime": "Unknown",
            "GPU": "Unknown",
            "Comments": "None",
            "Legend": (False, ""),
        }

    def restore_saved_properties(self) -> None:
        """Fetch stored metadata and return a bool if any could (or could not) be found."""
        if self.uses_saved_properties is not None:
            return

        self.define_properties()

        try:
            # Time section
            restoring_time: bool = record_exists(self.hash, "Time")
            if restoring_time:
                stored_time = read_record(self.hash, "Time")
                offset: float = stored_time["Offset"]
                start: int = stored_time["Start"]
                end: int = stored_time["End"]

                if start < end and (end - start) > 1 and (max(self.elapsed_time()) + offset) > 0:
                    self.offset_time_axis(offset)
                    self.offset = start
                    self.height = end
                else:
                    self.reset_time_axis()
                    StatusBarWithQueue.post(f"⚠ Rejected time offset for {self.name}.")

            # File properties section
            stored_properties = read_record(self.hash)
            self.uses_saved_properties = bool(stored_properties)
            if self.uses_saved_properties:
                self.properties = {**self.properties, **stored_properties}
        except Exception as e:
            self.uses_saved_properties = False
            self.reset_time_axis()
            log_exception(logger, e, "Failed to restore file metadata")

    def column(self, column_name: str = "None", index: int = None) -> Series:
        """Return a column view matching the provided string or a zeroed array.

        Todo:
            * Explore using offset+index for single position lookups

        Args:
            * column_name (str, optional): Header search string. Defaults to "None".
            * index (optional): Slice indices for modifying returned rows.

        Returns:
            * ndarray: Returns a view of the header-matched column.
        """
        col = self.zero_col  # Default to zeroed array matching current dimensions

        if column_name in {"None", "Index"} or column_name not in self.headers:
            return col

        try:
            if index is None:
                col = self.data.loc[self.offset : self.height - 1, column_name]
            else:
                col = self.data.at[index, column_name]
        except Exception as e:
            logger.error(f"Error returning {column_name}[{self.offset}:{self.height - 1}]")
            log_exception(logger, e)
        finally:
            return col

    def column_by_alias(self, generic_phrase: str = "None", index: int = None) -> Series:
        """Return a column using a header alias rather than an explicit term."""
        if generic_phrase == "None":
            return self.column()

        header: str = self.header_by_alias(generic_phrase)
        result = self.column(header, index)

        if result is None:
            return self.column()

        # Only return when phrase maps to one column or zero (e.g., when trimming the time axis)
        if len(result.shape) < 2:
            return result

        logger.info(f"{self.name} contains duplicate columns mapped to '{generic_phrase}'")
        return self.column()

    @stopwatch(silent=True)
    def infer_polling_rate(self, time_data: Series) -> float:
        """Infer the polling rate from elapsed time data, ignoring rollovers and large values."""
        try:
            positive_deltas = self.positive_time_deltas(time_data)

            if len(positive_deltas) == 0 or max(positive_deltas) == 0:
                logger.error(
                    "File does not have sufficient time data to infer polling rate - assuming 1000 ms"
                )
                if self.integrity == Integrity.Ideal:
                    self.integrity = Integrity.Dirty
                return 1.0  # seconds

            return self.filter_time_deltas(positive_deltas)
        except Exception as e:
            log_exception(logger, e, "Failed to obtain polling rate")
            return 1.0  # seconds

    def positive_time_deltas(self, time_data: Series) -> Series:
        """Return a Series of positive time deltas."""
        datetimes: Series = to_datetime(time_data, format=self.timestamp(self.version))
        deltas: Series = datetimes[1:].values.astype(float) - datetimes[:-1].values.astype(float)
        return deltas[deltas > 0]

    def filter_time_deltas(self, positive_deltas: Series) -> float:
        """Filter out very large time deltas from the positive time delta data."""
        polling_rates: Series = positive_deltas / 1_000_000_000
        median_rate: float = median(polling_rates)
        stdev_rate: float = std(polling_rates)
        stdev_str: str = ""

        if stdev_rate > 0:
            # Filter out time deltas that are greater than three times the standard deviation.
            polling_rates = polling_rates[median_rate + (stdev_rate * 3) > polling_rates]
            median_rate = median(polling_rates)
            stdev_rate = std(polling_rates)
            stdev_str = f" (±{stdev_rate * 1000:.1f} ms)" if stdev_rate > 0 else ""

        logger.debug(f"Median polling rate: {median_rate * 1000:.1f} ms{stdev_str}")
        return median_rate

    def reset_time_axis(self, remove_time_record: bool = True) -> None:
        """Reset start/end points and set initial timestamp to zero."""
        self.offset = 0
        self.height = self.data.shape[0]
        self.start_time_at_zero()
        self.resize_zero_column()
        self.evaluate_integrity()

        if remove_time_record:
            remove_record(self.hash, "Time")

    def start_time_at_zero(self) -> None:
        """Set the first visible time stamp to zero. Works with full and trimmed data sets."""
        time_alias: str = self.header_by_alias("Elapsed Time")
        initial_timestamp = self.column(time_alias, index=self.offset)
        self.data[time_alias] = round(self.data[time_alias] - initial_timestamp, 9)

        first_timestamp: float = self.column(time_alias, index=0)
        if first_timestamp != 0:
            update_record(self.hash, {"Offset": first_timestamp}, "Time")

    def update_time_metadata(self) -> None:
        """Update the time metadata for a capture file's record."""
        initial_timestamp: float = float(self.column_by_alias("Elapsed Time", index=0))

        if initial_timestamp == 0 and self.offset == 0 and self.height == self.data.shape[0]:
            return remove_record(self.hash, "Time")

        update_record(
            file_hash=self.hash,
            properties={
                "Offset": initial_timestamp,
                "Start": int(self.offset),
                "End": int(self.height),
            },
            section="Time",
        )

    @stopwatch(silent=True)
    def offset_time_axis(self, time_offset: float) -> None:
        """Shift the file's time series according to how the user dragged it along the plot."""
        if time_offset == 0:
            return

        self.data[self.header_by_alias("Elapsed Time")] += time_offset

    def trim_time_axis(self, relation: str = "Before", cutoff: float = 0) -> None:
        """Adjust the 'active' portion of a file, primarily reducing."""
        try:
            full_time_series: Series = self.data[self.header_by_alias("Elapsed Time")]

            if relation in {"Before", "Drop"}:
                less_than_cutoff_index: int = sum(full_time_series < cutoff)
                self.offset = (
                    less_than_cutoff_index
                    if relation == "Before"
                    else max([self.offset, less_than_cutoff_index])
                )
            else:
                full_height: int = full_time_series.shape[0]
                greater_than_cutoff_index: int = sum(full_time_series > cutoff)

                if greater_than_cutoff_index < full_height:
                    self.height = full_height - greater_than_cutoff_index

            # Reset any changes that would cause a plot's time to be fully negative or trimmed
            if self.offset >= self.height or self.frames() < 2:
                StatusBarWithQueue.post(f"⚠ Rejected time offset for {self.name}")
                self.reset_time_axis()

            self.update_time_metadata()
            self.resize_zero_column()
            self.evaluate_integrity()
        except Exception as e:
            log_exception(logger, e, "Trimming failed with time axis")

    @stopwatch(silent=True)
    def elapsed_time(self) -> ndarray:
        """Return the time data of the log."""
        return self.column_by_alias("Elapsed Time").to_numpy()

    @stopwatch(silent=True)
    def frametimes(self, fps: bool = False) -> ndarray:
        """Return the performance series of the log."""
        ft: Series = self.column_by_alias("Frametimes")
        return (1000 / ft if fps else ft).to_numpy()

    @stopwatch(silent=True)
    def frame_variation(self) -> ndarray:
        """Return the frame-to-frame variations of the log."""
        ft: Series = self.column_by_alias("Frametimes")
        return abs(ft - ft.shift()).to_numpy()

    def tainted_frametimes(self) -> bool:
        """Return a bool indicating whether the capture has valid performance data."""
        has_fps: bool = self.alias_present("Frametimes")
        if not has_fps:
            return True

        ft: ndarray = self.frametimes()
        return has_fps and (min(ft) == 0 or isinf(max(ft)) or any(isnan(ft)))

    @stopwatch(silent=True)
    def stutter(self, overwrite: bool = False) -> tuple:
        """Return the stutter data of the log."""
        if overwrite or self.stutter_data is None:
            self.stutter_data = self.calculate_stutter()

        return self.stutter_data

    @stopwatch(silent=True)
    def unsynced_frames(self) -> Series:
        """Return the unsynchronized frames of the log."""
        return self.column_by_alias("Unsynchronized Frames")

    @stopwatch(silent=True)
    def latency(self) -> Series:
        """Return the system latency data of the log."""
        return self.column_by_alias("System Latency")

    @stopwatch(silent=True)
    def power(self, source: str) -> Series:
        """Return the power data of the log."""
        return self.column_by_alias(source)

    @stopwatch(silent=True)
    def perf_per_watt(self, source: str) -> Series:
        """Return the perf/watt data of the log."""
        # Skip capture files that do not have a performance alias
        if not self.alias_present("Frametimes"):
            return self.column()

        fps: ndarray = self.frametimes(fps=True)
        pwr: ndarray = self.power(source)

        # Test for NaNs and infs
        bad_fps: bool = not any(isfinite(fps)) or max(fps) == 0
        bad_pwr: bool = not any(isfinite(pwr)) or max(pwr) == 0

        return self.column() if bad_fps or bad_pwr else Series(fps / pwr)

    @stopwatch(silent=True)
    def frequency(self, component: str) -> Series:
        """Return the component frequency data of the log."""
        return self.column_by_alias(f"{component} Frequency")

    @stopwatch(silent=True)
    def temperature(self, component: str) -> Series:
        """Return the component temperature data of the log."""
        return self.column_by_alias(f"{component} Temperature")

    @stopwatch(silent=True)
    def utilization(self, component: str) -> Series:
        """Return the component utilization data of the log."""
        return self.column_by_alias(f"{component} Utilization")

    @stopwatch(silent=True)
    def voltage(self, component: str) -> Series:
        """Return the component voltage data of the log."""
        return self.column_by_alias(f"{component} Voltage")

    @stopwatch(silent=True)
    def battery_charge_rate(self) -> Series:
        """Return the component utilization data of the log."""
        return self.column_by_alias("Battery Charge Rate")

    @stopwatch(silent=True)
    def battery_level(self) -> Series:
        """Return the component utilization data of the log."""
        return self.column_by_alias("Battery Level")
