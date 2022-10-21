# ┌──────────────────────────┐
# │ PYDRA by ANDREW NALAVANY │
# └──────────────────────────┘

"""Initializes the script."""

import sys
from multiprocessing import freeze_support
from traceback import extract_tb

from PyQt6 import QtCore
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import QApplication

from core.configuration import running_from_exe, save_config
from core.fileloader import FileLoader
from core.logger import get_logger, log_chapter, logging_startup
from core.stopwatch import Timekeeper, stopwatch
from gui.dialogs.main_window import MainWindow
from gui.plotobject import PlotObject
from gui.styles import register_fonts

logger = get_logger(__name__)


def startup() -> None:
    """Prepare application for execution."""
    logging_startup()

    # Install an exception hook to prevent uncaught exceptions from crashing the frozen application
    if running_from_exe():
        import pyi_splash

        sys.excepthook = trap_exceptions
        pyi_splash.update_text("Building GUI...")


@stopwatch
def main() -> None:
    """Launch the GUI."""
    app = QApplication(sys.argv)
    register_fonts()  # Sets default font
    app.setFont(QFontDatabase.font("Open Sans", "Regular", 8))
    app.setEffectEnabled(Qt.UIEffect.UI_AnimateMenu)
    window = MainWindow()

    window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    window.show()
    app.exec()

    return app, window


def shutdown() -> None:
    """Save the user configuration and records session statistics."""
    save_config()

    log_chapter(logger, "Session Information")
    window.report_memalloc_stats()
    PlotObject.report_cache_stats()
    FileLoader.report_thread_associations()
    Timekeeper.report_func_stats()


def trap_exceptions(exc_type, _, traceback) -> None:
    """Catch unhandled exceptions and log them rather than crashing."""
    frame = extract_tb(traceback)[0]
    file_path = frame.filename
    file_name = str.split(file_path, "\\", maxsplit=file_path.count("\\") - 1)[-1]

    log_chapter(logger, section_name="UNHANDLED EXCEPTION")
    logger.warning(f"[{frame.lineno}] {file_name}: {str(exc_type)[8:-2]}")
    log_chapter(logger)


# Start Qt event loop
if __name__ == "__main__":
    # Add support for multiprocessing when freezing to Windows executable
    freeze_support()

    app, window = None, None
    startup()

    # Initialize GUI and run the main loop. Anything after this block is part of the shutdown process.
    if (sys.flags.interactive != 1) or not hasattr(QtCore, "PYQT_VERSION"):
        # app = QApplication(sys.argv)
        # window = MainWindow()
        app, window = main()

    shutdown()
