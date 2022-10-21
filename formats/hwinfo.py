"""This module is responsible for handling HWiNFO capture files."""

from core.configuration import setting
from core.logger import get_logger, log_exception
from core.stopwatch import stopwatch
from formats.integrity import Integrity
from numpy import array, float32, max, min, nan, ndarray, sum
from pandas import DataFrame, Series, read_csv

from formats.capturefile import CaptureFile

logger = get_logger(__name__)


class HWiNFO(CaptureFile):
    """Base class for HWiNFO capture file types."""

    TIMESTAMP_FORMAT: str = "%H:%M:%S.%f"
    HEADER_ALIASES: dict[str, dict[str, str]] = {
        "7.14": {
            "Elapsed Time": "Time",
            "Frametimes": "Framerate [FPS]",  # Passed through RTSS
            "GPU Board Power": "GPU Power [W]",
            "GPU Chip Power": "GPU ASIC Power [W]",
            "GPU Frequency": "GPU Clock [MHz]",
            "GPU Temperature": "GPU Temperature [°C]",
            "GPU Utilization": "GPU D3D Usage [%]",
            "GPU Voltage": "GPU Core Voltage [V]",
            "CPU Power": "CPU Package Power [W]",
            "CPU Frequency": "Core Clocks (avg) [MHz]",
            "CPU Temperature": "CPU Package [°C]",
            "CPU Utilization": "Core Utility (avg) [%]",
            "Battery Charge Rate": "Charge Rate [W]",
            "Battery Level": "Charge Level [%]",
        },
    }

    __slots__ = ("devices", "polling_rate")

    def __init__(self, **kwargs) -> None:
        try:
            super().__init__(**kwargs)
            self.integrity = Integrity.Pending
            self.data, self.headers, self.height = self.parse_file()
            self.define_properties()

            # HWiNFO can relay performance metrics from RTSS
            self.integrity = Integrity.Partial
        except Exception as e:
            log_exception(logger, e, "Failed to read HWiNFO file")

    def extract_headers(self) -> list[str]:
        """Grab end-of-file headers.

        These will include column names that did not initially contain data at the beginning of
        the file (e.g., the battery discharge rate). These names are provided to Pandas read_csv()
        since Pandas will otherwise throw an error due to a mismatched number of columns.
        """
        headers: list[str] = []
        devices: list[str] = []

        with open(self.path, "r") as f:
            headers, devices = f.readlines()[-2:]
            self.devices = devices.split(",")

        # Date and Time headers appear without quotations and will always appear at the beginning
        # of the file. Including double quotations in the delimiter sequence is intentional: HWiNFO
        # has several headers that include commas - sometimes several.
        headers = ["Date", "Time"] + [h.replace('"', "") for h in headers.split('",')]
        headers[2] = str(headers[2])[10:]
        return headers

    @stopwatch(silent=True)
    def read_log(self) -> DataFrame:
        """Read a log file and returns the data in a DataFrame.

        Returns:
            * DataFrame: Returns the file's full data block.
        """
        data: DataFrame = DataFrame()
        headers: list[str] = self.extract_headers()
        column_names: list[int] = list(range(len(headers)))

        data = read_csv(
            self.path,
            delimiter=",",
            names=column_names,
            skiprows=1,
            skipfooter=2,
            engine="python",
            encoding="unicode_escape",
        )

        # Use headers obtained from end of file
        data.columns = headers
        return data

    @stopwatch(silent=True)
    def parse_file(self) -> tuple:
        """Call `read_log()` to obtain the log's actual data, then infer polling rate.

        Elapsed time is written to the Time column using the median of up to 50 time deltas.

        Limitations:
            * Appended logs are not supported.
            * Appended logs with varying tracked headers will throw an error.

        Returns:
            * tuple: File data, headers, and number of rows.
        """
        file_data: DataFrame = DataFrame()
        headers: list[str] = []
        height: int = 0

        try:
            file_data = self.read_log()
            height = file_data.shape[0]
            self.polling_rate = super().infer_polling_rate(file_data["Time"])

            # Replace NaNs after compression in case there are fully NA columns
            file_data = self.compress_dataframe(file_data)
            file_data = file_data.replace(nan, 0)  # Pandas method breaks with Categorical dtype

            # Write new time data to prevent precision errors from compression
            file_data["Time"] = array(file_data.index * self.polling_rate, dtype=float32)
            headers = file_data.columns.values.tolist()
        except Exception as e:
            log_exception(logger, e, "Error while parsing HWiNFO file")
        finally:
            return (file_data, headers, height)

    def define_properties(self) -> None:
        """Detect and report capture metadata for use in the stat table."""
        if self.uses_saved_properties or "GPU Hot Spot Temperature [°C]" not in self.headers:
            return

        hotspot_index = self.headers.index("GPU Hot Spot Temperature [°C]")
        self.properties["GPU"] = self.devices[hotspot_index].split(": ")[1]

    def relative_index(self, category: str) -> int:
        """Find the proper relative position of an aliased header for the active GPU.

        This is only necessary when a log contains metrics for multiple GPUs. The active GPU will
        have been defined in __init__() according to the associated device header for the GPU
        hotspot header.
        """
        category_name: str = self.header_by_alias(category)
        headers = range(len(self.headers))
        matching_indices: list[int]

        matching_indices = [idx for idx in headers if self.headers[idx] == category_name]

        for idx in matching_indices:
            if self.properties["GPU"] in self.devices[idx]:
                return matching_indices.index(idx)

    def frametimes(self, *args, **kwargs) -> ndarray:
        """Not yet implemented."""
        return self.column()

    def frequency(self, component: str) -> Series:
        """Return the component frequency data of the log."""
        results = super().frequency(component)
        if len(results.shape) == 1:
            return results

        return results.iloc[:, self.relative_index("GPU Frequency")]

    def temperature(self, component: str) -> Series:
        """Return the component temperature data of the log."""
        results = super().temperature(component)
        if len(results.shape) == 1:
            return results

        return results.iloc[:, self.relative_index("GPU Temperature")]

    def power(self, source: str) -> Series:
        """Return the power data of the log."""
        results = super().power(source)
        if len(results.shape) == 1:
            return results
        return results.iloc[:, self.relative_index(source)]

    def utilization(self, component: str) -> Series:
        """Return the component utilization data of the log."""
        results = super().utilization(component)
        if len(results.shape) == 1:
            return results
        return results.iloc[:, self.relative_index("GPU Utilization")]

    @stopwatch(silent=True)
    def project_battery_life(self) -> float:
        """Estimate the full battery life given a capture's duration and discharge rate."""
        try:
            battery_life: Series = self.column_by_alias("Battery Level")
            max_level: int = max(battery_life)
            min_level: int = min(battery_life)

            valid_max: bool = max_level >= int(setting("BatteryLife", "BatteryMaxLevel"))
            valid_min: bool = min_level <= int(setting("BatteryLife", "BatteryMinLevel"))

            if not valid_max or not valid_min:
                return 0

            charge_rate: Series = self.column_by_alias("Battery Charge Rate")
            negative_rates: int = sum(charge_rate < 0) + 2

            capture_lifetime: float = negative_rates * self.polling_rate
            time_per_unit_level: float = capture_lifetime / (max_level - min_level)
            return time_per_unit_level * 100
        except Exception as e:
            log_exception(logger, e, "Battery life projection failed")
            return 0
