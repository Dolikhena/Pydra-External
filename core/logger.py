"""This module manages the logging facilities for the application."""

import logging
from datetime import datetime
from os.path import getctime
from pathlib import Path
from traceback import extract_tb
from typing import Callable

from core.configuration import running_from_exe, session, setting
from core.signaller import StringSignaller

# Config file settings
_FOLDER_NAME: str = setting("Logger", "LoggingPath")

# Logging path constants
_FOLDER_PATH: Path = Path(_FOLDER_NAME).resolve()
_PATH_EXISTS: bool = _FOLDER_PATH.exists()
_FOLDER_PATH.mkdir(exist_ok=True)

# Log file constants
_LOG_NAME: str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
_LOG_FILE: str = f"{_FOLDER_NAME}{_LOG_NAME}.log"
_MSG_LENGTH: int = 97
_MSG_FORMAT: str = "%(asctime)s  %(thread)-6d %(module)-12s %(levelname)-9s %(message)s"
_LOG_FORMAT = logging.Formatter(_MSG_FORMAT, datefmt="%Y-%m-%d  %H:%M:%S")


class GUILogger(logging.Handler):
    """Provide a subclassed logging handler that uses Qt signals to redirect messages to the UI.

    Args:
        * logging (Handler): Logging handler created from the main window.
    """

    def __init__(self, callback: Callable) -> None:
        """Set up for the GUI Logger object."""
        super(GUILogger, self).__init__()
        self.setLevel(logging.DEBUG)
        self.setFormatter(_LOG_FORMAT)

        # Connect signals/slots for QObject interposer
        self.signaller = StringSignaller()
        self.signaller.signal.connect(callback)

    def emit(self, record: logging.LogRecord) -> None:
        """Allow for emitting a Qt signal when receiving log records.

        Formatted messages that exceed 149 chars and have a DEBUG/INFO level are split across lines
        to improve legibility of the GUI widget. This has no effect on messages written to the file.
        """
        msg = self.format(record)
        if (
            len(record.message) < 150
            or record.levelno > 20
            or record.funcName in {"log_exception", "profile_function"}
        ):
            return self.signaller.signal.emit(msg)

        prefix_len: int = len(msg) - len(record.message)
        msg_prefix: str = msg[:prefix_len]
        msg_segments = [
            record.message[i : i + _MSG_LENGTH] for i in range(0, len(record.message), _MSG_LENGTH)
        ]

        for chunk in msg_segments:
            self.signaller.signal.emit(msg_prefix + chunk)


def logging_path() -> str:
    """Return the absolute path for the current logging location."""
    return _FOLDER_PATH


def get_logger(name: str) -> logging.Logger:
    """Communicable logger object with unified formatting."""
    # Elevate default log level when running unit tests for legibility
    running_unit_tests: bool = any(
        "unittests" in name for name in logging.root.manager.loggerDict.keys()
    )

    # Root logger
    logger: logging.Logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # If running the app, create a file handler and set default log levels to DEBUG (10)
    if not running_unit_tests:
        logfile = logging.FileHandler(_LOG_FILE, encoding="utf-8")
        logfile.setFormatter(_LOG_FORMAT)
        logfile.setLevel(logging.DEBUG)
        logger.addHandler(logfile)

    return logger


def adjust_log_levels(level: int) -> None:
    """Adjust all child logger thresholds.

    Useful when suspending/resuming logging on-the-fly, like when repeating function calls with
    `stopwatch(iterations=n)`.
    """
    loggers: list[logging.Logger] = [
        logging.getLogger(name) for name in logging.root.manager.loggerDict
    ]
    for logger in loggers:
        logger.setLevel(level)


def format_table(table: dict, headers: tuple = ("Property", "Value")) -> list:
    """Take a dictionary and format its keys and values into a list of formatted strings.

    Args:
        * table (dict): A dictionary containing the rows and values to be printed. This can be a
        simple flat dict or each key can have multiple values, which are then broken out into
        multiple columns.
        * headers (tuple, optional): Must match the number of keys and values in table dict.
        Defaults to ("Property", "Value").
    """
    cols: int = len(headers)
    keys: list[str] = list(table.keys())
    values: list = list(table.values())
    one_value: bool = not isinstance(values[0], tuple)

    # Set column widths to match their longest strings
    widths: list[int] = [0] * cols
    if one_value:
        widths = [
            max(max(len(str(x)) for x in table), len(headers[0])),
            max(max(len(str(x)) for x in table.values()), len(headers[1])),
        ]

    else:
        widths[0] = max(max(len(str(x)) for x in table), len(headers[0]))
        for item in values:
            for index, value in enumerate(item):
                index += 1
                widths[index] = max(len(str(value)), len(headers[index]), widths[index])

    def table_line(left: str, mid: str, right: str) -> str:
        """Draw boundary lines for tables."""
        line: str = left
        for index in range(cols):
            line += f"{'─'.ljust(2 + widths[index], '─')}" + (mid if index + 1 < cols else right)
        return line

    # Shapes for table outlines
    table_top: str = table_line("┌", "┬", "┐")
    table_mid: str = table_line("├", "┼", "┤")
    table_btm: str = table_line("└", "┴", "┘")

    def table_text(contents: tuple) -> str:
        """Combine text and separators to create each row in the table."""
        text: str = "│"
        for i, val in enumerate(contents):
            if not isinstance(val, tuple):
                # Catch section breaks in single column tables and return a pre-formatted string
                if "-----" in contents:
                    return table_mid
                text += f" {str(val).ljust(widths[i])} │"
            else:
                for j, t_val in enumerate(val):
                    # Catch section breaks for multi-column tables
                    if "-----" in str(t_val):
                        return table_mid
                    j += 1
                    text += f" {str(t_val).ljust(widths[j])} │"
        return text

    # Create the table, starting from the top row
    formatted_table: list[str] = [table_top, table_text(headers), table_mid]

    # Append each row of the table
    for index, value in enumerate(values):
        formatted_table.append(table_text((keys[index], value)))

    # Append the bottom row
    formatted_table.append(table_btm)

    return formatted_table


def log_chapter(logger: logging.Logger, section_name: str = "") -> None:
    """Output a uniformly-formatted line break and section header for the log."""
    logger.debug("".center(_MSG_LENGTH, "─"))
    if section_name != "":
        logger.debug(f" {section_name} ".upper().center(_MSG_LENGTH, " "))


def log_table(logger: logging.Logger, table: dict, headers: tuple = ("Property", "Value")) -> None:
    """Log the keys and values of a formatted table.

    Args:
        * logger (logging.Logger): Logger object that belongs to the calling module.
        * table (dict): A dictionary containing the rows and values to be printed. This can be a
        simple flat dict or each key can have multiple values, which are then broken out into
        multiple columns.
        * headers (tuple, optional): Must match the number of keys and values in table dict.
        Defaults to ("Property", "Value").
    """
    formatted_table: list[str] = format_table(table, headers)
    for row in formatted_table:
        logger.debug(row)


def log_exception(logger: logging.Logger, exc: Exception, msg: str = "UNHANDLED EXCEPTION") -> None:
    """Provide a descriptive format for recording exceptions in other modules.

    This will print the Exception type, the module it was caught in, and the line number along with
    the code from that line.
    """
    traceback = extract_tb(exc.__traceback__)[0]
    file_path: str = traceback.filename
    file_name: str = str.split(file_path, "\\", maxsplit=file_path.count("\\") - 1)[-1]
    line_num: int = traceback.lineno

    log_chapter(logger, section_name=msg.upper())
    logger.error(f"[{line_num}] {file_name}: {str(type(exc))[8:-2]} ({exc})")
    if not running_from_exe():
        logger.error(f"> {traceback.line}")
    logger.error(logger.findCaller(stack_info=True)[3])
    log_chapter(logger)


def logging_startup() -> None:
    """Perform basic startup tasks for the logging facility.

    Creates the root logger, checks for an existing output folder, removes old log files if the
    number exceeds `MAX_FILE_COUNT`, and prints the initial ini settings.
    """
    logger = get_logger(__name__)
    log_chapter(logger, "Logging Setup")
    logger.debug(f"Logging path: {logging_path()}")
    logger.debug(f"Log format: {_MSG_FORMAT}")

    if _PATH_EXISTS:

        def folder_contents() -> list:
            """Return the number of files in the log folder."""
            return list(_FOLDER_PATH.iterdir())

        max_file_count: int = int(setting("Logger", "MaxFiles"))
        num_of_logs: int = len(folder_contents())

        # Check if the number of logs exceeds the maximum amount
        if num_of_logs > max_file_count:
            file_list: list = folder_contents()
            removed_logs: int = num_of_logs - max_file_count
            logger.debug(
                f"Removed {removed_logs} log file{'s' if removed_logs > 1 else ''} "
                f"(max: {max_file_count})"
            )

            # Remove oldest excess file(s) from logging path
            for _ in range(removed_logs):
                oldest_file: str = min(file_list, key=getctime)
                Path(oldest_file).unlink()
                file_list.pop(file_list.index(oldest_file))

        # Return folder size (in KB) after culling old logs
        num_of_logs = len(folder_contents())
        folder_size = sum(f.stat().st_size for f in folder_contents() if f.is_file()) / 1000
        logger.debug(
            f"Log folder contains {num_of_logs} file{'s' if num_of_logs > 1 else ''} "
            f"with a total size of {folder_size:.1f} KB"
        )
    else:
        logger.debug(f"Folder '{_FOLDER_NAME}' was created")

    logger.debug(f"Log file for this session: {_LOG_FILE}")

    # Log the current settings in user config file
    log_config_file(logger)


def log_config_file(logger: logging.Logger) -> None:
    """Print the config.ini values at startup."""
    try:
        if not session("ExistingConfig"):
            logger.debug("Created config file using default values")
        else:
            log_chapter(logger, "Config Settings")
            with open(Path("config.ini").resolve()) as cfg:
                for line in cfg:
                    logger.debug(line.strip())
    except Exception as e:
        log_exception(logger, e)
