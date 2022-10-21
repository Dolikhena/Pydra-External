"""This module is responsible for handling FrameView capture files."""

from core.configuration import setting, setting_bool
from core.logger import get_logger, log_exception
from core.stopwatch import stopwatch
from core.utilities import vendor_gpu_substrings
from numpy import any, max, min, sum
from pandas import Series

from formats.presentmon import InspectionItem, PresentMon

logger = get_logger(__name__)

_SECOND_GENERATION: set[str] = ("1.1", "1.2", "1.4")
_VENDOR_SUBSTRINGS = vendor_gpu_substrings()


class FrameView(PresentMon):
    """Class for parsing FrameView log files."""

    # Dictionary for fetching the preferred version-specific headers from generic phrases
    HEADER_ALIASES: dict[str, dict[str, str]] = {
        "1.4": {
            "System Latency": "MsPCLatency",
        },
        "1.2": {
            "Battery Charge Rate": "Battery Drain Rate(W)",
            "Battery Level": "Battery Percentage",
        },
        "1.1": {
            "NVIDIA GPU Chip Power": "GPUOnlyPwr(W) (API)",
            "NVIDIA GPU Board Power": "NV Pwr(W) (API)",
            "AMD GPU Chip Power": "AMDPwr(W) (API)",
            "System Latency": "MsRenderPresentLatency",
            "GPU Frequency": "GPU0Clk(MHz)",
            "GPU Temperature": "GPU0Temp(C)",
            "GPU Utilization": "GPU0Util(%)",
            "CPU Power": "CPU Package Power(W)",
            "CPU Frequency": "CPUClk(MHz)",
            "CPU Temperature": "CPU Package Temp(C)",
            "CPU Utilization": "CPUUtil(%)",
        },
        "1.0": {
            "Elapsed Time": "TimeInSeconds",
            "Frametimes": "MsBetweenPresents",
            "Render Present Latency": "MsUntilDisplayed",
            "Unsynchronized Frames": "AllowsTearing",
            "NVIDIA GPU Chip Power": "GPUOnlyPower(W)",
            "NVIDIA GPU Board Power": "TotalPower(W)",
            "AMD GPU Chip Power": "AMDPower(W)",
        },
    }
    # Incremental header changes
    HEADER_ALIASES["1.1"] = HEADER_ALIASES["1.0"] | HEADER_ALIASES["1.1"]
    HEADER_ALIASES["1.2"] = HEADER_ALIASES["1.2"] | HEADER_ALIASES["1.1"]
    HEADER_ALIASES["1.4"] = HEADER_ALIASES["1.2"] | HEADER_ALIASES["1.4"]

    # Dictionary for fetching fallback headers from generic phrases
    FALLBACK_HEADER_ALIASES: dict[str, dict[str, str]] = {
        "1.4": {
            "System Latency": "MsRenderPresentLatency",
        },
        # "1.1": {
        #     "Frametimes": "MsBetweenDisplayChange",
        # },
        # "1.0": {
        #     "Frametimes": "MsBetweenDisplayChangeActual",
        # },
    }

    # Characteristics that have significant impact on capture integrity
    MAJOR_INSPECTION_ITEMS: dict[str, tuple] = {
        "1.1": (  # 1.2 and 1.4 also share these criteria
            "GPU Consistency",
            "CPU Consistency",
            "Resolution Consistency",
            "Resolution Validity",
            "Process ID Consistency",
        ),
        "1.0": (
            "Application Consistency",
            "Swapchain Address Consistency",
            "Runtime Consistency",
            "No Dropped Frames",
            "Present Mode Consistency",
            "Hardware-Based Present Mode",
        ),
    }
    # Incremental criteria changes
    MAJOR_INSPECTION_ITEMS["1.1"] = MAJOR_INSPECTION_ITEMS["1.0"] + MAJOR_INSPECTION_ITEMS["1.1"]
    MAJOR_INSPECTION_ITEMS["1.4"] = MAJOR_INSPECTION_ITEMS["1.2"] = MAJOR_INSPECTION_ITEMS["1.1"]

    def power(self, source: str) -> Series:
        """Return the performance data of the log."""
        if source == "CPU":
            return self.column_by_alias("CPU Power")

        gpu_property: str = self.properties["GPU"].upper()
        vendor: str = ""

        if any(s in gpu_property for s in _VENDOR_SUBSTRINGS["NVIDIA"]):
            vendor = "NVIDIA"
        elif any(s in gpu_property for s in _VENDOR_SUBSTRINGS["AMD"]):
            vendor = "AMD"
        elif any(s in gpu_property for s in _VENDOR_SUBSTRINGS["INTEL"]):
            vendor = "Intel"
        else:
            vendor = "Unknown"

        return self.column_by_alias(f"{vendor} {source} Power")

    @stopwatch
    def inspect_capture(self) -> dict[str, InspectionItem]:
        """Check specific fields in the capture for validity and consistency.

        Header                     Tests                 Version
        ========================================================
        Present Latency            Type                     1.1+
        GPU                        Uniformity               1.1+
        CPU                        Uniformity               1.1+
        Resolution                 Uniformity, Type         1.1+
        Process ID                 Uniformity               1.1+
        ========================================================
        Application                Uniformity                1.0
        Runtime                    Uniformity, Type          1.0
        Allows Tearing             Type                      1.0
        Swap Chain Address         Uniformity                1.0
        Sync Interval              Type                      1.0
        Present Flags              Uniformity                1.0
        Present Mode               Uniformity, Type          1.0
        Dropped Frames             Uniformity                1.0
        MsBetweenDisplayChange     Type                      1.0

        Raises:
            * NotImplementedError: Raised when an unsupported FrameView capture is being parsed.

        Returns:
            * dict: Tests and boolean results, which can be extended to include version-exclusive
            fields.
        """
        # Check if fallback headers are necessary
        self.register_fallbacks()

        # Basic Presentmon inspection
        inspection_results: dict[str, InspectionItem] = super().inspect_capture()

        try:
            if self.version in _SECOND_GENERATION:
                versioned_inspection: dict[str, InspectionItem] = self.second_gen_inspection()

                # Merge versioned and basic PresentMon results
                inspection_results = versioned_inspection | inspection_results
        except Exception as e:
            log_exception(logger, e, "FrameView inspection failed")
            return {"FrameView inspection failed": str(e)}
        finally:
            self.log_inspection_report(inspection_results)
            return inspection_results

    def register_fallbacks(self) -> None:
        """Perform checks to determine if the capture should use alternate headers."""
        if self.version != "1.4":
            return

        # MsPCLatency will be NA if the application does not support the latest Reflex SDK
        try:
            latency: str = "System Latency"
            header: str = self.header_by_alias(latency)
            present: bool = header == self.preferred_aliases(latency) and header in self.headers

            valid: bool = min(self.column(header)) != 0
            if present and valid and latency in self.fallbacks_in_use:
                self.remove_fallback_header(latency)
            elif not (present and valid) and latency not in self.fallbacks_in_use:
                self.register_fallback_header(latency)
        except Exception:
            self.register_fallback_header(latency)

    def second_gen_inspection(self) -> dict[str, InspectionItem]:
        """Perform validity/consistency checks for second-gen FV files."""
        default = InspectionItem.default_result()
        pc_latency_validity = default
        gpu_consistency = default
        cpu_consistency = default
        resolution_consistency = default
        resolution_validity = default
        pid_consistency = default

        try:
            data = None
            mode = None  # Most common value in the column
            violations = 0  # Number of suboptimal values
            result = False  # Result of test for nominal values

            data = self.column_by_alias("System Latency")
            result = min(data) != 0 and "System Latency" not in self.fallbacks_in_use
            pc_latency_validity = InspectionItem(
                result,
                0 if result else self.frames(),
                f"{'(Using fallback header)' if 'System Latency' in self.fallbacks_in_use else ''} "
                f"System latency data contains zero or NA values",
            )

            mode, result, violations = self.inspect_consistency("GPU")
            gpu_consistency = InspectionItem(
                result,
                violations,
                f"GPU model name ({mode}) was not consistent across all frames",
            )

            mode, result, violations = self.inspect_consistency("CPU")
            cpu_consistency = InspectionItem(
                result,
                violations,
                f"CPU model name ({mode}) was not consistent across all frames",
            )

            mode, result, violations = self.inspect_consistency("Resolution")
            resolution_consistency = InspectionItem(
                result,
                violations,
                f"Resolution ({mode}) was not consistent across all frames",
            )

            data = self.column("Resolution")
            result = (
                data[0] != "WINDOWED"
                if resolution_consistency.passed
                else "WINDOWED" not in data.unique()
            )
            resolution_validity = InspectionItem(
                result,
                0 if result else len(data[data == "WINDOWED"]),
                "Application was running in a window",
            )

            mode, result, violations = self.inspect_consistency("ProcessID")
            pid_consistency = InspectionItem(
                result,
                violations,
                f"Process ID ({mode}) was not consistent across all frames",
            )
        except Exception as e:
            log_exception(logger, e, "FrameView v1.1+ inspection failed")
        finally:
            return {
                "Valid System Latency": pc_latency_validity,
                "GPU Consistency": gpu_consistency,
                "CPU Consistency": cpu_consistency,
                "Resolution Consistency": resolution_consistency,
                "Resolution Validity": resolution_validity,
                "Process ID Consistency": pid_consistency,
                "section_1": "-----",
            }

    def gpu_property(self) -> str:
        """Detect the type and number of GPUs used in the capture.

        Raises:
            * NotImplementedError: Raised when parsinng an unsupported file version.

        Returns:
            * str: GPU vendor (NVIDIA, AMD, Intel) and model (e.g., GeForce RTX 3080).
        """
        drop_na_columns: bool = setting_bool("General", "DropNAColumns")
        if self.version in _SECOND_GENERATION:
            number_of_GPUs: int = (
                sum(x in self.headers for x in ("GPU0Clk(MHz)", "GPU1Clk(MHz)"))
                if drop_na_columns
                else sum(any(self.column(x)) for x in ("GPU0Clk(MHz)", "GPU1Clk(MHz)"))
            )

            gpu_name: str = str(self.column("GPU", index=0))
            if number_of_GPUs > 1 or not self.consistent_property("GPU"):
                gpu_name += "*"
        elif self.version == "1.0":
            number_of_GPUs = 1  # There is no way of determining the GPU topology in FV 1.0

            # Use power column inclusion (or values, if NA columns are not dropped) to infer what
            # GPU manufacturer was captured in this file
            if drop_na_columns:
                gpu_name = (
                    "NVIDIA GPU"
                    if self.alias_in_headers("NV GPU Board Power")
                    else "AMD GPU"
                    if self.alias_in_headers("AMD GPU Chip Power")
                    else "Intel GPU"
                )
            else:
                nv_gpu: bool = max(self.column_by_alias("NV GPU Board Power"), 0) > 0
                amd_gpu: bool = max(self.column_by_alias("AMD GPU Chip Power"), 0) > 0
                gpu_name = "NVIDIA GPU" if nv_gpu else "AMD GPU" if amd_gpu else "Intel GPU"
        else:
            raise NotImplementedError("Unsupported FrameView version")

        if self.version != "1.0" and number_of_GPUs > 1:
            gpu_name += " (Multi-GPU)"

        return gpu_name

    def define_properties(self) -> None:
        """Detect and report capture metadata for use in the stat table."""
        if self.uses_saved_properties:
            return self.verify_saved_properties()

        self.properties["Application"] = self.application_property()
        self.properties["Resolution"] = self.consistent_and_valid_property("Resolution")
        self.properties["Runtime"] = self.consistent_and_valid_property("Runtime")
        self.properties["GPU"] = self.gpu_property()

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
            time: Series = Series(self.elapsed_time()).where(charge_rate < 0, None)
            capture_lifetime: float = (negative_rates / self.height) * (max(time) - min(time))
            time_per_unit_level: float = capture_lifetime / (max_level - min_level)
            return time_per_unit_level * 100
        except Exception as e:
            log_exception(logger, e, "Battery life projection failed")
            return 0
