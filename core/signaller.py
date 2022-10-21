"""Provides modules with a unified method for emitting Qt signals from non-Qt objects."""

from PyQt6.QtCore import QObject, pyqtSignal


class ObjectSignaller(QObject):
    """Helper class to provide generic Qt signals to non-Qt objects."""

    signal = pyqtSignal(object)


class StringSignaller(QObject):
    """Helper class to provide string-typed Qt signals to non-Qt objects."""

    signal = pyqtSignal(str)


class IntSignaller(QObject):
    """Helper class to provide int-typed Qt signals to non-Qt objects."""

    signal = pyqtSignal(int)


class FloatSignaller(QObject):
    """Helper class to provide float-typed Qt signals to non-Qt objects."""

    signal = pyqtSignal(float)


class TupleSignaller(QObject):
    """Helper class to provide a tuple of Qt signals to non-Qt objects."""

    signal = pyqtSignal(tuple)


class ExceptionSignaller(QObject):
    """Helper class to provide Exception-typed Qt signals to non-Qt objects."""

    signal = pyqtSignal(Exception)
