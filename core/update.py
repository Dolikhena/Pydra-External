"""This module reports if a newer build is available from GitHub."""

from collections import namedtuple
from pathlib import Path
from re import compile, search
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from core.configuration import app_root, running_from_exe, session, set_value, setting, setting_bool
from core.logger import get_logger, log_chapter, log_exception

logger = get_logger(__name__)
Version: namedtuple = namedtuple("Version", ["major", "minor", "patch", "build"])

_VERSION_PATTERN = compile(r".*(filevers=\(\d+, \d+, \d+, \d+\)),")
_RAW_FILE_URL: str = "https://raw.githubusercontent.com/Dolikhena/Pydra-External/main/version.rc"
_TIMEOUT: int = int(setting("Development", "UpdateTimeout"))


def update_available() -> tuple[bool, bool]:
    """Check the current build version against GitHub and return True if an update is available."""
    newer_build_available: bool = False
    config_out_of_date: bool = False

    try:
        logger.debug(f"Version: {current_version_str()}, build {_CURRENT.build}")
        config_out_of_date = compare_config_version()
        latest = latest_version()

        if running_from_exe():
            new_major: bool = latest.major > _CURRENT.major
            new_minor: bool = latest.minor > _CURRENT.minor
            new_patch: bool = latest.patch > _CURRENT.patch

            if new_major or new_minor or new_patch:
                newer_build_available = True

                logger.info(
                    f"A newer executable is available: {latest.major}.{latest.minor}.{latest.patch}"
                )
        elif latest.build > _CURRENT.build:
            newer_build_available = True
            logger.info(f"A newer build is available on GitHub: {latest.build}")
    except Exception as e:
        log_exception(logger, e, "Failed to check for update")
        newer_build_available = False
    finally:
        log_chapter(logger)
        return (newer_build_available, config_out_of_date)


def latest_version() -> Version[int, int, int, int]:
    """Return the latest version, obtained from a raw GitHub file."""
    version_str: tuple[int, int, int, int] = (0, 0, 0, 0)
    try:
        with urlopen(_RAW_FILE_URL, timeout=_TIMEOUT) as response:
            data = response.read().decode("utf-8")
            version_str = parse_version_file(data)
    except (HTTPError, URLError) as e:
        logger.error(f"Could not establish connection to GitHub: {e}")
    except Exception as e:
        log_exception(logger, e)
    finally:
        return Version(version_str[0], version_str[1], version_str[2], version_str[3])


def current_version() -> Version[int, int, int, int]:
    """Return the current version, obtained from the version resource file."""
    version_str: tuple[int, int, int, int] = (0, 0, 0, 0)
    try:
        version_file: str = (Path(app_root()) / "version.rc").read_text("utf-8")
        version_str = parse_version_file(version_file)
    except FileNotFoundError as e:
        logger.error(f"Could not locate version resource file: {e}")
    except Exception as e:
        log_exception(logger, e)
    finally:
        return Version(version_str[0], version_str[1], version_str[2], version_str[3])


def current_version_str() -> str:
    """Return the current version as a string."""
    return f"{_CURRENT.major}.{_CURRENT.minor}.{_CURRENT.patch}"


def parse_version_file(version_file) -> Version[int, int, int, int]:
    """Parse the local/remote version resource file and return the version numbers as a tuple."""
    try:
        version_str = search(_VERSION_PATTERN, version_file).group(0)
        version_str = version_str.replace("(", ")")
        version_str = version_str.split(")")[1].split(", ")
        return Version(
            int(version_str[0]), int(version_str[1]), int(version_str[2]), int(version_str[3])
        )
    except Exception as e:
        log_exception(logger, e, "Could not determine local config version")
        return Version(0, 0, 0, 0)


def compare_config_version() -> bool:
    """Compare the current config version against the latest version."""
    out_of_date: bool = False
    try:
        config_str: str = setting("General", "Version")

        if config_str == "0.0.0":
            # Config version is out of date
            if session("ExistingConfig"):
                return True

            # Config file was just created
            set_value("General", "Version", current_version_str())
            return False

        config_str = config_str.split(".")
        config_version = Version(int(config_str[0]), int(config_str[1]), int(config_str[2]), 0)

        if setting_bool("General", "KeepOldConfig"):
            out_of_date = (
                _CURRENT.major > config_version.major
                or _CURRENT.minor > config_version.minor
                or _CURRENT.patch - config_version.patch > 1
            )

        else:
            out_of_date = (
                _CURRENT.major > config_version.major
                or _CURRENT.minor > config_version.minor
                or _CURRENT.patch > config_version.patch
            )

    except Exception as e:
        log_exception(logger, e, "Could not determine config file version")
    return out_of_date


_CURRENT: Version = current_version()
