"""This module manages creation, reading, and updating the config file."""

import sys
from configparser import NoSectionError, RawConfigParser
from contextlib import suppress
from pathlib import Path
from typing import Any

_ROOT_PATH: Path = Path(__file__).parents[1]
_CONFIG_PATH: Path = Path("config.ini").resolve()
_CONFIG_EXISTS: bool = _CONFIG_PATH.exists()
_PARSER = RawConfigParser()
_PARSER.optionxform = str  # Preserve case when writing
_RUN_FROM_EXE: bool = getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")

# Temporary variables that are read and updated between multiple modules
_SESSION: dict[str, Any] = {
    "CurrentTabIndex": 0,
    "DarkMode": None,
    "EnableScatterPlots": False,
    "ExistingConfig": _CONFIG_EXISTS,
    "FileDisplayFormat": "File Name",
    "PrimaryDataSource": "",
    "SecondaryDataSource": "",
    "SelectedFilePath": "",
    "ShowCrosshairs": False,
    "ShowOutliers": False,
    "ShowRSquaredValue": False,
    "SwappingSources": False,
}


def session(option: str) -> Any:
    return _SESSION[option]


def set_session_value(option: str, new_value: Any) -> None:
    """Write the new value of a session value."""
    _SESSION[option] = new_value


# Default config values
DEFAULTS: dict[str, dict[str, str]] = {
    "General": {
        "Version": "0.0.0",
        "KeepOldConfig": "False",
        "UseDarkStylesheet": "True",
        "TimeScale": "Seconds",
        "DiminishFallbacks": "True",
        "LastUsedPath": "",
        "MaxIOThreads": "8",
        "DropNAColumns": "True",
        "CompressionMinSizeMB": "20",
        "DecimalPlaces": "2",
    },
    "Plotting": {
        "Renderer": "Software",
        "Antialiasing": "Enabled",
        "PlotEmptyData": "False",
        "NormalAlpha": "224",
        "EmphasizedAlpha": "255",
        "DiminishedAlpha": "32",
        "AxisLabelFontSize": "8",
        "AxisLabelOffset": "6",
        "AxisTickLength": "-8",
        "MainTitleFontSize": "14",
        "MainTitleFormat": "<b>[DataSource]</b> | [Application] ([Runtime]) at [Resolution] w/ [GPU]",
        "LegendItemFormat": "[FileName] | [Comments]",
        "LegendItemFontSize": "10",
    },
    "Crosshair": {
        "CursorUpdateRate": "30",
        "UseDownsampling": "Automatic",
        "SampleRate": "1",
    },
    "Line": {
        "ClampXMinimum": "True",
        "ClampYMinimum": "True",
    },
    "Percentiles": {
        "ClampYMinimum": "True",
        "PercentileStart": "90.000",
        "PercentileEnd": "99.999",
        "PercentileStep": "0.010",
    },
    "Histogram": {
        "ClampXMinimum": "True",
        "ClampYMinimum": "True",
        "HistogramBinSize": "0",
    },
    "Box": {
        "ClampXMinimum": "True",
        "ClampYMinimum": "True",
        "OutlierValues": "Min/Max Values",
        "HideLegend": "True",
        "Height": "30",
        "Spacing": "35",
    },
    "Scatter": {
        "ClampXMinimum": "True",
        "ClampYMinimum": "True",
    },
    "Experience": {
        "CalloutTextSize": "10",
        "HideLegend": "True",
        "Height": "30",
        "Spacing": "33",
    },
    "StutterHeuristic": {
        "StutterDeltaMs": "4.0",
        "StutterDeltaPct": "20.0",
        "StutterWindowSize": "19",
        "StutterWarnPct": "1.0",
        "StutterWarnAvg": "60.0",
        "StutterWarnMax": "200.0",
    },
    "OscillationHeuristic": {
        "TestForOscillation": "True",
        "OscDeltaMs": "4.0",
        "OscDeltaPct": "20.0",
        "OscWarnPct": "3.0",
    },
    "BatteryLife": {
        "BatteryMaxLevel": "98",
        "BatteryMinLevel": "3",
    },
    "Exporting": {
        "SavePath": "saved/",
        "ImageFormat": "PNG",
    },
    "Logger": {
        "LoggingPath": "logs/",
        "MaxFiles": "20",
    },
    "Metadata": {
        "ExpirationTime": "7",
    },
    "Statistics": {
        "PercentileMethod": "Inclusive",
        # Base64 JSON
        "Visibility": 'eyJDYXB0dXJlXG5UeXBlIjogdHJ1ZSwgIkNhcHR1cmVcbkludGVncml0eSI6IHRydWUsICJBcHBsaWNhdGlvbiI6IHRydWUsICJSZXNvbHV0aW9uIjogdHJ1ZSwgIlJ1bnRpbWUiOiB0cnVlLCAiR1BVIjogdHJ1ZSwgIkNvbW1lbnRzIjogdHJ1ZSwgIkR1cmF0aW9uIChzKSI6IHRydWUsICJOdW1iZXJcbm9mIEZyYW1lcyI6IGZhbHNlLCAiU3luY2VkXG5GcmFtZXMiOiBmYWxzZSwgIk1pbmltdW0gRlBTIjogZmFsc2UsICJBdmVyYWdlIEZQUyI6IHRydWUsICJNZWRpYW4gRlBTIjogZmFsc2UsICJNYXhpbXVtIEZQUyI6IGZhbHNlLCAiMC4xJSBMb3cgRlBTIjogdHJ1ZSwgIjAuMSUgRlBTIjogdHJ1ZSwgIjElIExvdyBGUFMiOiB0cnVlLCAiMSUgRlBTIjogdHJ1ZSwgIjUlIEZQUyI6IGZhbHNlLCAiMTAlIEZQUyI6IGZhbHNlLCAiMC4xJSBMb3cgRlBTXG4vIEF2ZXJhZ2UgRlBTIjogZmFsc2UsICIwLjElIEZQU1xuLyBBdmVyYWdlIEZQUyI6IGZhbHNlLCAiMSUgTG93IEZQU1xuLyBBdmVyYWdlIEZQUyI6IGZhbHNlLCAiMSUgRlBTXG4vIEF2ZXJhZ2UgRlBTIjogZmFsc2UsICI1JSBGUFNcbi8gQXZlcmFnZSBGUFMiOiBmYWxzZSwgIjEwJSBGUFNcbi8gQXZlcmFnZSBGUFMiOiBmYWxzZSwgIk51bWJlciBvZlxuU3R1dHRlciBFdmVudHMiOiBmYWxzZSwgIlByb3BvcnRpb25cbm9mIFN0dXR0ZXIiOiB0cnVlLCAiQXZlcmFnZVxuU3R1dHRlciI6IHRydWUsICJNYXhpbXVtXG5TdHV0dGVyIjogdHJ1ZSwgIkF2ZXJhZ2UgU3lzdGVtXG5MYXRlbmN5IChtcykiOiB0cnVlLCAiQXZlcmFnZSBQZXJmLVxucGVyLVdhdHQgKEYvSikiOiB0cnVlLCAiQXZlcmFnZSBHUFVcbkJvYXJkIFBvd2VyIChXKSI6IHRydWUsICJBdmVyYWdlIEdQVVxuQ2hpcCBQb3dlciAoVykiOiBmYWxzZSwgIkF2ZXJhZ2UgR1BVXG5GcmVxdWVuY3kgKE1IeikiOiB0cnVlLCAiQXZlcmFnZSBHUFVcblRlbXBlcmF0dXJlIChcdTAwYjBDKSI6IHRydWUsICJBdmVyYWdlIEdQVVxuVXRpbGl6YXRpb24gKCUpIjogdHJ1ZSwgIkF2ZXJhZ2UgR1BVXG5Wb2x0YWdlIChWKSI6IGZhbHNlLCAiQXZlcmFnZSBDUFVcblBvd2VyIChXKSI6IGZhbHNlLCAiQXZlcmFnZSBDUFVcbkZyZXF1ZW5jeSAoTUh6KSI6IGZhbHNlLCAiQXZlcmFnZSBDUFVcblRlbXBlcmF0dXJlIChcdTAwYjBDKSI6IGZhbHNlLCAiQXZlcmFnZSBDUFVcblV0aWxpemF0aW9uICglKSI6IGZhbHNlLCAiQXZlcmFnZSBCYXR0ZXJ5XG5DaGFyZ2UgUmF0ZSAoVykiOiBmYWxzZSwgIlByb2plY3RlZFxuQmF0dGVyeSBMaWZlIChzKSI6IGZhbHNlLCAiRmlsZSBOYW1lIjogdHJ1ZSwgIkZpbGUgTG9jYXRpb24iOiB0cnVlfQ==',
    },
    "Development": {
        "StopwatchCI": "95.0",
        "StopwatchStdError": "0.05",
        "StopwatchTimeLimit": "3",
        "TimekeeperKey": "Total",
        "SignalProxyRate": "30",
        "UpdateTimeout": "10",
    },
}


# The widgets controlling these settings will receive a tinted
# background if the user changes their value away from the default.
FUNCTIONAL_SETTINGS = (
    "StutterDeltaMs",
    "StutterDeltaPct",
    "StutterWindowSize",
    "OscDeltaMs",
    "OscDeltaPct",
)


def app_root() -> str:
    """Get the application's root path (used for relative paths like icons and file output)."""
    return str(_ROOT_PATH)


def running_from_exe() -> bool:
    """Indicate whether the program is running from an interpreter or frozen executable."""
    return _RUN_FROM_EXE


def save_config() -> None:
    """Write the current config settings to file (minus the dev section if run from frozen exe)."""
    if _RUN_FROM_EXE:
        _PARSER.remove_section("Development")

    # Suppress permission errors from not having local write permissions
    with suppress(PermissionError):
        with open(_CONFIG_PATH, "w") as new_cfg:
            _PARSER.write(new_cfg)


def set_defaults(version: str = "") -> None:
    """Restore all of the predefined settings and values for the config file."""
    for key in DEFAULTS.keys():
        _PARSER[key] = DEFAULTS[key]

    if version:
        _PARSER["General"]["Version"] = version

    # Save the defaulted file
    save_config()


def default_value(section: str, option: str) -> bool:
    """Return the result of a boolean comparison between a setting and its default value."""
    return _PARSER.get(section, option) == DEFAULTS[section][option]


def setting_bool(section: str, option: str, **kwargs) -> bool:
    """Return the string comparison result for a config value."""
    return setting(section, option, **kwargs) == "True"


def setting_exists(section: str, option: str) -> bool:
    """Check if a setting exists in the config file."""
    return _PARSER.has_option(section, option)


def setting(section: str, option: str, default: bool = False, **kwargs) -> str:
    """Attempt to fetch a setting from a given section of the config file.

    If the setting option does not exist, create it using the default values. If the section
    itself does not exist, then the config file is likely out of date and should be reset.
    """
    config_value: str
    try:
        config_value = DEFAULTS[section][option]
        if default or (_RUN_FROM_EXE and section == "Development"):
            return config_value

        config_value = _PARSER.get(section, option, **kwargs)

        # Use default value if an empty string is about to be returned
        if not config_value.strip():
            raise ValueError
    except Exception:
        # If a setting cannot be found, write it using the default value
        try:
            _PARSER.set(section, option, config_value)
        except NoSectionError:
            # If an entire section is missing, revert the config file to default values. This
            # should only be encountered after a major update or accidental user edit.
            set_defaults()
    finally:
        return config_value


def set_value(section: str, option: str, new_value: Any) -> None:
    """Write the new value of a setting into the config parser object.

    If the value can be meaningfully typecast as a float - that is, not ending with .0 - round
    to the third decimal place to avoid rounding errors (e.g., 0.010000000000000002 when 0.01
    was specified.)
    """
    new_value = str(new_value)

    # Skip assignment if the value will not be changed, or fetch the
    # default value if that key does not exist for whatever reason
    if new_value == _PARSER.get(section, option, fallback=DEFAULTS):
        return

    try:
        if "." not in new_value:
            return

        # Avoid rounding errors by limiting precision to three decimal places. This also avoids
        # needlessly casting integers as floats, which can throw ValueErrors elsewhere.
        new_value = str(round(float(new_value), 3))
    except ValueError:
        pass  # Don't do anything if the float assertion fails
    finally:
        _PARSER.set(section, option, new_value)


# Set defaults if config.ini doesn't exist or is empty
if not _CONFIG_PATH.exists() or _CONFIG_PATH.stat().st_size == 0:
    set_defaults()

# Update the parser object to match config.ini at runtime
with suppress(PermissionError):
    _PARSER.read(_CONFIG_PATH)
