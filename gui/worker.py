"""This module provides a worker class with support for Qt signals.

Each worker runs on their own thread, separate from the main GUI thread, but must respect Python's
GIL (global interpreter lock) all the same.
"""
from typing import Callable

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot


class WorkerSignals(QObject):
    """Define the signals that can be emitted from a running worker thread.

    Supported signals:
        * error = pyqtSignal(str)
        * result = pyqtSignal(object)
        * finished = pyqtSignal()
    """

    error = pyqtSignal(Exception)
    result = pyqtSignal(object)
    finished = pyqtSignal(bool)


class Worker(QRunnable):
    """Worker object for running a passed function on a non-GUI thread.

    Subclasses QRunnable to interface with QThreadpool, which spins up a maximum number of threads
    unlike QThread which requires more direct management over creation, execution, and destruction.
    Also uses the WorkerSignals class to emit signals during processing, which QRunnable does not
    natively support.
    """

    __slots__ = ("fn", "args", "kwargs", "signals")

    def __init__(self, fn, *args, **kwargs) -> None:
        super().__init__()
        self.fn: Callable = fn
        self.args: tuple = args
        self.kwargs: dict = kwargs
        self.signals: WorkerSignals = WorkerSignals()

    @pyqtSlot(bool)
    def work(self) -> None:
        """Process the passed function and connected signals."""
        aborted: bool = False
        try:
            func = self.fn(*self.args, **self.kwargs)
            self.signals.result.emit(func)
        except RuntimeError:
            aborted = True
        except Exception as e:
            self.signals.error.emit(e)
        finally:
            if not aborted:
                self.signals.finished.emit(True)
