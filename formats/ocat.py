"""This module is responsible for handling OCAT capture files."""

from typing import Union

from core.logger import get_logger, log_exception
from core.stopwatch import stopwatch
from pandas import read_csv

from formats.presentmon import InspectionItem, PresentMon

logger = get_logger(__name__)


class OCAT(PresentMon):
    """Class for parsing OCAT log files."""

    # Dictionary for fetching version-specific headers from generic phrases
    # Another alias dictionary may be necessary to track future changes in the system info block
    HEADER_ALIASES: dict[str, dict[str, str]] = {
        "1.6.1": {
            "Elapsed Time": "TimeInSeconds",
            "Frametimes": "MsBetweenPresents",
            "Render Present Latency": "MsUntilDisplayed",
            "Unsynchronized Frames": "AllowsTearing",
            "System Latency": "MsEstimatedDriverLag",
        }
    }

    # Inspection fields that have significant impact on capture integrity
    MAJOR_INSPECTION_ITEMS: dict[str, tuple] = {
        "1.6.1": (
            "Resolution Consistency",
            "Resolution Validity",
            "Application Consistency",
            "Swapchain Address Consistency",
            "Runtime Consistency",
            "Process ID Consistency",
            "No Dropped Frames",
            "Present Mode Consistency",
            "Hardware-Based Present Mode",
        ),
    }

    __slots__ = "property_fields"

    @stopwatch
    def inspect_capture(self) -> dict[str, Union[bool, str]]:
        """Check specific fields in the capture for validity and consistency.

        Header                         Tests             Ver
        ====================================================
        Application              Uniformity              1.6
        Runtime                  Uniformity, Type        1.6
        Allows Tearing           Type                    1.6
        Swap Chain Address       Uniformity              1.6
        Sync Interval            Type                    1.6
        Present Flags            Uniformity              1.6
        Present Mode             Uniformity, Type        1.6
        Dropped Frames           Uniformity              1.6
        MsBetweenPresents        Uniformity              1.6
        Resolution               Uniformity, Type        1.6

        Raises:
            * NotImplementedError: Raised when an unsupported OCAT capture is being parsed.

        Returns:
            * dict: Tests and boolean results, which can be extended to include version-exclusive
            fields.
        """
        # Basic Presentmon inspection
        inspection_results: dict[str, InspectionItem] = super().inspect_capture()

        try:
            versioned_inspection = self.ocat_inspection()

            # Combine versioned and basic PresentMon results
            inspection_results = versioned_inspection | inspection_results
        except Exception as e:
            log_exception(logger, e, "OCAT inspection failed")
            return {"OCAT inspection failed": str(e)}
        finally:
            self.log_inspection_report(inspection_results)
            return inspection_results

    def ocat_inspection(self) -> dict[str, InspectionItem]:
        """Perform validity/consistency checks for OCAT files."""
        default = InspectionItem.default_result()
        resolution_consistency = default
        resolution_validity = default
        pid_consistency = default

        try:
            data = None
            mode = None  # Most common value in the column
            violations = 0  # Number of suboptimal values
            result = False  # Result of test for nominal values

            mode, result, violations = self.inspect_consistency("Resolution")
            resolution_consistency = InspectionItem(
                result,
                violations,
                f"Resolution ({mode}) was not consistent across all frames",
            )

            data = self.column("Resolution")
            mode = data.mode()[0]
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
                "Resolution Consistency": resolution_consistency,
                "Resolution Validity": resolution_validity,
                "Process ID Consistency": pid_consistency,
                "section_1": "-----",
            }

    def define_properties(self) -> None:
        """Detect and report capture metadata for use in the stat table."""
        if self.uses_saved_properties:
            return self.verify_saved_properties()

        all_properties = read_csv(
            self.path, engine="c", sep=",", nrows=1, usecols=self.property_fields
        )

        self.properties["Application"] = self.application_property()
        self.properties["Resolution"] = self.consistent_and_valid_property("Resolution")
        self.properties["Runtime"] = self.consistent_and_valid_property("Runtime")
        self.properties["GPU"] = all_properties.at[0, "GPU"]
