"""This module provides unified signal values for context menus created by various widgets."""

from enum import Enum, auto

from core.signaller import IntSignaller


class MenuOption(Enum):
    """Symbols denoting context menu options selected by the user.

    A value is emitted by a function that is connected to the MainWindow.context_menu_signals().
    """

    # Mouse controls and actions
    ToggleCursor = auto()
    PlotDragged = auto()
    PlotDropped = auto()

    # Plot/curve controls
    SelectFile = auto()
    ClearFile = auto()
    ClearAllFiles = auto()
    ModifySelectedFile = auto()
    ModifyAllFiles = auto()
    RefreshPlots = auto()
    ReorderLegend = auto()

    # File actions
    ViewInBrowser = auto()
    ViewProperties = auto()


class ContextSignal:
    """This class provides a single line of communication between widgets and the main menu."""

    emitter: IntSignaller = IntSignaller()

    @classmethod
    def emit(cls, value) -> None:
        cls.emitter.signal.emit(value)
