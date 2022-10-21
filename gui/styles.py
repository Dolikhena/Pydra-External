"""This module provides stylesheets to multiple modules based on user preference."""

from pathlib import Path

from core.configuration import app_root, running_from_exe, session

from PyQt6.QtGui import QFontDatabase, QIcon

_HOT_RELOAD: bool = not running_from_exe() and False  # Set to True to reload styles
_GUI_PATH: Path = Path(app_root()) / "gui"
_LIGHT_STYLESHEET: str = (_GUI_PATH / "light.css").read_text()
_DARK_STYLESHEET: str = (_GUI_PATH / "dark.css").read_text()


# PyQt6 no longer uses resource files, so we need to route icon paths manually
def as_posix(stylesheet: str) -> str:
    """Convert relative paths in a stylesheet to posix paths."""
    return stylesheet.replace("url(/", f"url({_GUI_POSIX_PATH}/")


_GUI_POSIX_PATH: str = _GUI_PATH.as_posix()
_LIGHT_STYLESHEET = as_posix(_LIGHT_STYLESHEET)
_DARK_STYLESHEET = as_posix(_DARK_STYLESHEET)


def icon_path(icon_name: str) -> QIcon:
    """Get the path to an icon resource. Required for freezing."""
    return QIcon(str(_GUI_PATH / "icons" / icon_name))


def register_fonts() -> None:
    """Get the path to typeface resource. Required for freezing."""
    for font_name in {"OpenSans-Regular.ttf", "OpenSans-Italic.ttf", "OpenSans-Bold.ttf"}:
        QFontDatabase.addApplicationFont(str(_GUI_PATH / "fonts" / font_name))


def current_stylesheet() -> str:
    """Return the chosen stylesheet."""
    if _HOT_RELOAD:
        style: str = (_GUI_PATH / f"{'dark' if session('DarkMode') else 'light'}.css").read_text()
        return as_posix(style)
    return _DARK_STYLESHEET if session("DarkMode") else _LIGHT_STYLESHEET
