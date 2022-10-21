"""This module contains a subclass for PyQt6's QStatusBar."""

from collections import deque
from typing import Callable

from core.logger import get_logger

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QStatusBar

logger = get_logger(__name__)

_SPECIAL_CHARS = ("⚠", "⭐")


class StatusBarWithQueue(QStatusBar):
    """Subclass of the status bar, modified to support automatic durations and public messages."""

    callback: Callable
    message_queue: deque = deque(maxlen=3)

    @classmethod
    def post(cls, message: str) -> None:
        """Route messages from external modules to the GUI instance.

        Args:
            * message (str): The text to display on the status bar.
        """
        if cls.callback is not None:
            cls.callback(message)

    def __init__(self, parent) -> None:
        super().__init__(parent=parent)
        self.set_callback()

    def set_callback(self) -> None:
        """Publicize the GUI status bar's message function to support messages from other modules.

        Args:
            * func (Callable): Function registered to the GUI status bar.
        """
        StatusBarWithQueue.callback = self.showMessage

    def process_queue(self) -> None:
        """Display the oldest message in the message queue."""
        if len(StatusBarWithQueue.message_queue) > 0:
            self.showMessage(StatusBarWithQueue.message_queue.popleft())

    def showMessage(self, message: str, msecs: int = 0) -> None:
        """Show a message in the status bar for 400-666 milliseconds per word (minimum of 2000).

        Normal messages are dispalyed for 400 milliseconds per word. Special messages are displayed
        for 666 milliseconds per word.

        If a message is currently displayed, append the message to a queue which will be checked
        100 milliseconds after the current message has been cleared.

        Args:
            * message (str): The text to display on the status bar.
            * msecs (int, optional): Unused. Only included to match overloaded signature.
        """
        if self.currentMessage() == "":
            msecs = max(
                message.count(" ")
                * (666 if any(char in message for char in _SPECIAL_CHARS) else 400),
                2000,
            )
            QTimer.singleShot(msecs + 100, self.process_queue)
            return super().showMessage(message, msecs)  # Exit method to avoid re-appending

        StatusBarWithQueue.message_queue.append(message)
