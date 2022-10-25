"""Base class for Presentmon-based capture file types."""

from core.exceptions import FileIntegrityError
from core.logger import get_logger, log_exception, log_table
from core.stopwatch import stopwatch
from numpy import any, average, max, min, ndarray, where
from pandas import DataFrame, Series, errors, read_csv
from pandas.errors import DtypeWarning

from formats.capturefile import CaptureFile, InspectionItem
from formats.integrity import Integrity

logger = get_logger(__name__)


class PresentMon(CaptureFile):
    """Base class for Presentmon-based capture file types."""

    # HEADER_ALIASES is defined in child modules

    __slots__ = ("inspection", "integrity_hash")

    def __init__(self, **kwargs) -> None:
        try:
            super().__init__(**kwargs)
            self.integrity = Integrity.Pending
            self.integrity_hash: int = -1
            self.data, self.headers, self.height = self.parse_file()
            self.evaluate_integrity()
        except Exception as e:
            log_exception(logger, e, "Failed to read PresentMon file")

    def evaluate_integrity(self) -> None:
        """Update inspection metrics before testing capture integrity."""
        try:
            current_hash: int = hash((self.height, self.offset))
            if current_hash == self.integrity_hash:
                return

            self.integrity_hash = current_hash
            self.inspection: dict[str, InspectionItem] = self.inspect_capture()
            self.define_properties()
            self.update_integrity_by_inspection(recheck=True)
        except Exception as e:
            log_exception(logger, e)

    def extract_headers(self) -> list[str]:
        """Get headers from header block, replacing the first two headers for consistency."""
        return list(read_csv(self.path, engine="python", nrows=1))

    @stopwatch(silent=True)
    def read_log(self) -> DataFrame:
        """Read a log file and returns the data in a DataFrame.

        Due to the large and unchanging number of headers in addition to per-frame sampling, these
        files often tend to be both wide AND tall, making them good candidates for compression.
        Similarly, all fully NA columns (e.g., CPU core utilization) will be dropped to further
        reduce memory usage.

        Raises:
            * errors.DtypeWarning: Raised when encountering a column with mixed data types, like a
            string in a column otherwise populated with floating-point values. This often indicates

        Returns:
            * Union[DataFrame, bool, integrity]: Returns the file's full data block, whether
            compression was performed, and the number of rows.
        """
        data: DataFrame = DataFrame()

        try:
            if self.app_name == "OCAT":
                data = self.read_ocat_log()
            else:
                # FrameView
                data = read_csv(self.path, sep=",", engine="c")

            # Catch errors in smaller files overlooked by pd.read_csv's chunking
            if any(data["Dropped"].isin(["Error"])):
                raise errors.DtypeWarning
        # Catch mixed data types, which generally indicate a major problem
        except KeyError as e:
            self.integrity = Integrity.Invalid
            raise FileIntegrityError("'Dropped' column not found") from e
        except DtypeWarning:
            data = self.process_mixed_dtypes()
        except Exception as e:
            self.integrity = Integrity.Invalid
            log_exception(logger, e)
        finally:
            return self.compress_dataframe(data)

    def read_ocat_log(self) -> DataFrame:
        """OCAT files requires some additional processing compared to FrameView."""
        capture_fields = self.extract_headers()
        property_fields = capture_fields[-4:]

        # OCAT appends some system information to the right-hand side of the capture which
        # is useful but will interfere with DataFrame compression, so we will handle it in
        # a separate method in the OCAT module
        self.property_fields = property_fields

        data = read_csv(self.path, sep=",", engine="c", usecols=capture_fields[:-11])

        # Combine the Width and Height columns into a single Resolution column
        data["Resolution"] = data["Width"].astype(str) + "x" + data["Height"].astype(str)
        data.drop(["Width", "Height"], axis=1, inplace=True)

        return data

    def process_mixed_dtypes(self) -> DataFrame:
        """Files containing multiple data types must be read with less performant arguments.

        Commonly, when an app loses focus during a capture, the dropped frame column will contain
        one or more "Error" values, which throws an error with Pandas' CSV reader.
        """
        logger.error("Rereading file due to mixed data types")

        self.integrity = Integrity.Mangled
        try:
            # Report indices of errors (+2 offset for spreadsheet views)
            dropped_col: Series = read_csv(
                self.path,
                usecols=["Dropped"],
                dtype=str,
                sep=",",
                engine="c",
                low_memory=False,
            ).squeeze("columns")

            rows_with_errors: ndarray = where(dropped_col == "Error")[0]
            if any(rows_with_errors):
                for row in rows_with_errors:
                    logger.error(f"Error in 'Dropped' column at row {row + 2:,}")
            else:
                logger.info("'Dropped' column OK, dtype issue is elsewhere")

            data = read_csv(self.path, sep=",", engine="c", low_memory=False)
        except Exception as e:
            self.integrity = Integrity.Invalid
            log_exception(logger, e)
        return data

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
            log_exception(logger, e, "Error while parsing PresentMon file")
        finally:
            return (file_data, headers, height)

    # def frametimes(self, fps: bool = False) -> ndarray:
    #     """Return the performance series of the log.

    #     Args:
    #         * fps (bool, optional): Express performance in frames per second. This is less accurate
    #         for representing performance but is easier for general understanding of trends. Defaults
    #         to False.

    #     Returns:
    #         * ndarray: Series of frame times or frame rates for the capture.
    #     """
    #     ft: Series = self.column(
    #         self.header_by_alias("Frametimes")
    #         if self.inspection.get("Display Change Validity", False)
    #         else "MsBetweenPresents"
    #     )

    #     return (1000 / ft if fps else ft).to_numpy()

    def inspect_consistency(self, header) -> tuple[str, bool, int]:
        """Check the consistency of a column's values."""
        mode: str = "Unknown"
        ideal: bool = False
        violations: int = self.frames()

        try:
            data: Series = self.column(header)
            mode = str(data.mode()[0])
            heuristic: int = data.nunique()
            ideal = heuristic == 1
            violations = 0 if ideal else len(data[data != data[0]])
        except Exception:
            logger.error(f"Encountered an error while inspecting {header}")
        finally:
            return mode, ideal, violations

    @stopwatch
    def inspect_capture(self) -> dict[str, InspectionItem]:
        """Check specific fields in any PresentMon-based capture for nominal values.

        Per-frame metadata can contain hints suggesting a capture was recorded in suboptimal
        conditions, such as an active synchronization policy, foreground focus loss, resolution
        changes, and more. Subclasses should override this method to check for specific fields
        in their captures.
        """
        default = InspectionItem.default_result()
        application_consistency = default
        swapchain_consistency = default
        runtime_consistency = default
        runtime_validity = default
        present_flags = default
        sync_policy_consistency = default
        sync_policy_validity = default
        tearing_validity = default
        dropped_frame_validity = default
        present_mode_consistency = default
        present_mode_validity = default
        disp_change_validity = default
        render_queue_depth = default

        try:
            data = None
            mode = None  # Most common value in the column
            heuristic = None  # How a column should be evaluated (uniques, min/max, etc.)
            violations = 0  # Number of suboptimal values
            result = False  # Result of test for nominal values

            # Consistency checks - columns should have exactly one unique value
            mode, result, violations = self.inspect_consistency("Application")
            application_consistency = InspectionItem(
                result,
                violations,
                f"Application name ({mode}) was not consistent across all frames",
            )

            mode, result, violations = self.inspect_consistency("SwapChainAddress")
            swapchain_consistency = InspectionItem(
                result,
                violations,
                f"Swapchain address ({mode}) was not consistent across all frames",
            )

            mode, result, violations = self.inspect_consistency("Runtime")
            runtime_consistency = InspectionItem(
                result,
                violations,
                f"Graphics runtime ({mode}) was not consistent across all frames",
            )

            _, result, violations = self.inspect_consistency("PresentFlags")
            present_flags = InspectionItem(
                result,
                violations,
                "Present flags were not consistent across all frames",
            )

            _, result, violations = self.inspect_consistency("SyncInterval")
            sync_policy_consistency = InspectionItem(
                result,
                violations,
                "Vertical synchronization policy changed during the capture",
            )

            mode, result, violations = self.inspect_consistency("PresentMode")
            present_mode_consistency = InspectionItem(
                result,
                violations,
                f"Flip model ({mode}) was not consistent across all frames",
            )

            # Validity checks - columns should contain specific values
            # The flip model should be hardware-based, but there are a few different types:
            #   HW Models (ideal)                           SW Models (compatibility mode)
            #     > Hardware: Legacy Flip                     > Composed: Flip
            #     > Hardware: Legacy Copy to front buffer     > Composed: Copy with GPU GDI
            #     > Hardware: Direct Flip                     > Composed: Copy with CPU GDI
            #     > Hardware: Independent Flip                > Composed: Composition Atlas
            #     > Hardware Composed: Independent Flip     Other (fallback value)
            # data is reused from previous test
            data = self.column("PresentMode")
            if present_mode_consistency.passed:
                result = "Hardware" in data[0]
            else:
                heuristic = data.unique()
                result = all("Hardware" in x for x in heuristic)
            present_mode_validity = InspectionItem(
                result,
                0 if result else len(data[~data.str.contains("Hardware")]),
                "Hardware-based flip model was not used during the capture",
            )

            data = self.column("SyncInterval")
            heuristic = max(data)
            result = heuristic < 1
            sync_policy_validity = InspectionItem(
                result,
                0 if result else len(data[data > 0]),
                "Vertical synchronization was active during the capture",
            )

            data = self.column_by_alias("Unsynchronized Frames")
            heuristic = max(data)
            result = heuristic != 0
            tearing_validity = InspectionItem(
                result,
                0 if result else self.frames(),
                "No tearing was observed in the capture (e.g., VRR may have been active)",
            )

            data = self.column_by_alias("Frametimes")
            heuristic = min(data)
            result = heuristic != 0
            disp_change_validity = InspectionItem(
                result,
                0 if result else len(data[data == 0]),
                "Zeros were detected in frame time data",
            )

            # Data variable is reused from previous test
            # This is essentially the same as the Render Queue Depth column from FrameView
            heuristic = average(self.column("MsUntilDisplayed") / data)
            result = heuristic < 1
            render_queue_depth = InspectionItem(
                result,
                0 if result else len(self.column("MsUntilDisplayed") > data),
                "Deep render queue (application may have used a borderless/windowed mode)",
            )

            data = self.column("Runtime")
            if runtime_consistency.passed:
                heuristic = self.column("Runtime", index=0)
                result = heuristic != "Other"
            else:
                heuristic = data.unique()
                result = "Other" not in heuristic
            runtime_validity = InspectionItem(
                result,
                0 if result else len(data[data == "Other"]),
                "Graphics runtime could not be determined",
            )

            data = self.column("Dropped")
            if "int" in str(data.dtype):
                heuristic = max(data)
                result = heuristic == 0
            else:
                result = False
            if not result:
                data = data.astype("string")
            dropped_frame_validity = InspectionItem(
                result,
                0 if result else len(data[~data.str.contains("0")]),
                "Frames were dropped during the capture",
            )
        except Exception as e:
            log_exception(logger, e, "PresentMon inspection failed")
        finally:
            return {
                "Application Consistency": application_consistency,
                "Swapchain Address Consistency": swapchain_consistency,
                "Runtime Consistency": runtime_consistency,
                "Runtime Validity": runtime_validity,
                "Present Flag Consistency": present_flags,
                "Sync Policy Consistency": sync_policy_consistency,
                "No Active Sync Policy": sync_policy_validity,
                "Tearing is Possible": tearing_validity,
                "No Dropped Frames": dropped_frame_validity,
                "Present Mode Consistency": present_mode_consistency,
                "Hardware-Based Present Mode": present_mode_validity,
                "Display Change Validity": disp_change_validity,
                "Render Queue Depth": render_queue_depth,
            }

    def passed_inspection(self) -> bool:
        """Returns True if all inspection items are passed."""
        return all(
            item.passed for item in self.inspection.values() if isinstance(item, InspectionItem)
        )

    def log_inspection_report(self, inspection_results: dict) -> None:
        """Report inspection results (preserving separators) to the session log."""
        table_headers = (
            f"{self.app_name} {self.version} Inspection",
            "Passed",
            "Errors",
            "Description",
        )
        report_table: dict[str, tuple] = {
            k: (
                v if isinstance(v, str) else v.passed,
                v if isinstance(v, str) else f"{v.violations:,}",
                v if isinstance(v, str) else "" if v.passed else v.description,
            )
            for k, v in inspection_results.items()
        }

        log_table(logger, report_table, table_headers)

    def update_integrity_by_inspection(self, recheck: bool = False) -> None:
        """Update file integrity following inspection.

        Assumes integrity has not been set elsewhere. E.g., in parse_file() due to dtype errors
        """
        if not (self.integrity is Integrity.Pending or recheck):
            return

        try:
            if self.passed_inspection():
                self.integrity = Integrity.Ideal
            else:
                major_items = [
                    self.inspection.get(field).passed
                    for field in self.MAJOR_INSPECTION_ITEMS[self.version]
                ]

                self.integrity = Integrity.Mangled if False in major_items else Integrity.Dirty
        except Exception as e:
            log_exception(logger, e)

    def application_property(self) -> str:
        """Return the first application name found. Add an asterisk if inspection is suboptimal."""
        first_result: str = str(self.column("Application", index=0))
        if not self.consistent_property("Application"):
            first_result += "*"
        return first_result

    def consistent_property(self, header) -> bool:
        """Return a bool indicating if a property has been deemed as consistent."""
        return self.inspection.get(f"{header} Consistency", False)

    def valid_property(self, header) -> bool:
        """Return a bool indicating if a property has been deemed as valid."""
        return self.inspection.get(f"{header} Validity", False)

    def consistent_and_valid_property(self, header) -> str:
        """Check if a column is both consistent and valid."""
        if header not in self.headers:
            return "Unknown"

        first_result: str = str(self.column(header, index=0))
        consistent = self.consistent_property(header)
        valid = self.valid_property(header)

        if not (consistent and valid):
            first_result += "*"

        return first_result

    def verify_saved_properties(self) -> None:
        """Check property validity using properties from saved metadata."""
        pairs: dict[str, bool] = {
            "Application": self.consistent_property("Application"),
            "Resolution": self.consistent_property("Resolution")
            and self.valid_property("Resolution"),
            "Runtime": self.consistent_property("Runtime") and self.valid_property("Runtime"),
            "GPU": self.consistent_property("GPU"),
        }

        for prop, verified in pairs.items():
            if not verified and not self.properties[prop].endswith("*"):
                self.properties[prop] = f"{self.properties[prop]}*"
            elif verified and self.properties[prop].endswith("*"):
                while self.properties[prop].endswith("*"):
                    self.properties[prop] = self.properties[prop].removesuffix("*")
