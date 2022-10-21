"""This module provides a decorator and context manager for code timing and profiling."""

from cProfile import Profile
from functools import wraps
from io import StringIO
from pstats import SortKey, Stats
from statistics import NormalDist
from time import perf_counter_ns
from typing import Callable

from numpy import argsort, average, empty, float32, max, median, min, ndarray, percentile, sqrt
from PyQt6.QtCore import QElapsedTimer

from core.configuration import running_from_exe, setting
from core.logger import adjust_log_levels, get_logger, log_table

logger = get_logger(__name__)

_TIME_LIMIT: int = int(setting("Development", "StopwatchTimeLimit"))
_CONFIDENCE_INTERVAL: float = float(setting("Development", "StopwatchCI")) / 100
_TARGET_ERROR: float = float(setting("Development", "StopwatchStdError")) / 100
_IGNORED_FUNCS: tuple = ("main", "read_log", "parse_file", "create_plot_object")


class Timekeeper:
    """Receives individual results from stopwatch() to track execution time trends."""

    measurements: dict[str, list] = {}

    @classmethod
    def record(cls, func_name: str, measurement: int) -> None:
        """Receive a measurement for a function and add/append it to the current table."""
        # Don't report stopwatch measurements for constructors or the main code block
        if func_name in {"main", "__init__"}:
            return

        # Append measurements to existing function entries or create a new key
        if func_name not in cls.measurements.keys():
            cls.measurements[func_name] = [measurement]
        else:
            cls.measurements[func_name].append(measurement)

    @classmethod
    def report_func_stats(cls) -> None:
        """Log a formatted table with basic insights from the session's tracked measurements."""
        headers: tuple[str, str, str, str, str, str, str]
        columnated_dict: dict[str, tuple]
        sorted_dict: dict[str, tuple]
        key: Callable

        key_mode: str = setting("Development", "TimekeeperKey")
        if key_mode == "Count":
            key = len
        elif key_mode == "Average":
            key = average
        elif key_mode == "Median":
            key = median
        elif key_mode == "Min":
            key = min
        elif key_mode == "Max":
            key = max
        else:
            key = sum  # Default

        headers = ("Measured Function", "Count", "Average", "Median", "Min", "Max", "Total")
        columnated_dict = {
            k: (
                key(v),  # Used for sorting. Removed before logging.
                f"{len(v):,}",
                time_from_ns(average(v)) if len(v) > 1 else "---",
                time_from_ns(median(v)) if len(v) > 1 else "---",
                time_from_ns(min(v)) if len(v) > 1 else "---",
                time_from_ns(max(v)) if len(v) > 1 else "---",
                time_from_ns(sum(v)),
            )
            for k, v in cls.measurements.items()
        }

        # Sort by key before writing to log
        sorted_dict = dict(sorted(columnated_dict.items(), key=lambda key: key[1], reverse=True))
        sorted_dict = {k: v[1:] for k, v in sorted_dict.items()}

        log_table(logger, sorted_dict, headers)


class context_stopwatch:
    """Context manager for timing a block of code.

    Results are tracked by Timekeeper. Entries will be preceded by an asterisk (*) to differentiate
    from functions wrapped by Stopwatch.
    """

    __slots__ = ("active", "description", "elapsed", "silent", "timer")

    def __init__(self, code_description: str = "", silent: bool = False) -> None:
        self.description: str = code_description or "undefined"
        self.timer: QElapsedTimer = QElapsedTimer()
        self.elapsed: int = 0
        self.active: bool = logger.level <= 10
        self.silent: bool = silent

    def __enter__(self) -> None:
        """Start the timer once the context manager is invoked."""
        if self.active:
            self.timer.start()

    def __exit__(self, *args) -> None:
        """Stop the timer and log the elapsed time once the managed code block has finished."""
        if self.active:
            self.elapsed = self.timer.nsecsElapsed()

            if not self.silent:
                logger.debug(f"** {self.description}: {time_from_ns(self.elapsed)}")

            Timekeeper.record(f"** {self.description}", self.elapsed)


def profile_function(func: Callable, args, kwargs) -> Callable:
    """Use the built-in func profiler on a function.

    This is only used for development. Results are logged but not tracked by Timekeeper.
    """
    pr: Profile = Profile()
    value: Callable

    # Toggle the profiler just before and immediately after executing the passed function
    pr.enable()
    value = func(*args, **kwargs)
    pr.disable()

    # Capture Profiler output from a text stream and redirect it to the log
    s = StringIO()
    ps = Stats(pr, stream=s).sort_stats(SortKey.CUMULATIVE)
    ps.print_stats()
    logger.debug(s.getvalue())
    return value


def measure_once(func: Callable, silent: bool = False, *args, **kwargs) -> tuple[Callable, int]:
    """Perform a function once and measure its execution time. Used for non-intrusive profiling."""
    timer: QElapsedTimer = QElapsedTimer()
    value: Callable

    # Start timer, execute the function, then calculate elapsed time
    timer.start()
    value = func(*args, **kwargs)
    elapsed_time: int = timer.nsecsElapsed()

    # Record the measured function's name and elapsed time to the log and Timekeeper
    if not silent:
        logger.debug(f"*  {func.__qualname__}: {time_from_ns(elapsed_time)}")
    Timekeeper.record(func.__name__, elapsed_time)

    return value, elapsed_time


def repeated_measurements(func: Callable, args, kwargs, iterations: int) -> tuple[Callable, int]:
    """Perform a function more than once, up to the established time limit.

    This is only used for development. Results are logged but not tracked by Timekeeper.
    """
    # Variable setup
    timer: QElapsedTimer = QElapsedTimer()
    prev_level: int = logger.level
    z: float = NormalDist().cdf(_CONFIDENCE_INTERVAL)
    w: Welford = Welford()
    value: Callable
    elapsed_time: int = 0

    # Exit reasons
    exit_reason: str = "None"
    exited_early: bool = False
    over_time: bool = False
    below_target_error: bool = False
    run_stats: dict[str, str] = {}

    # Initialize ndarray to hold the individual loop times
    run_times: ndarray = empty((iterations), dtype=float32)

    logger.info(
        f"Suspending logging while profiling {func.__qualname__} over {iterations:,} calls..."
    )

    # Elevate log to ERROR threshold during repeated measurements to reduce verbosity and overhead.
    adjust_log_levels(40)

    # Track elapsed time and forcibly exit the loop if it has run for too long
    max_time: float = perf_counter_ns() + (_TIME_LIMIT * 1_000_000_000)

    for i in range(iterations):
        # Follow the same process as measure_once()
        timer.start()
        value = func(*args, **kwargs)
        elapsed_time = timer.nsecsElapsed()

        # Add the current iteration's elapsed time to the list of all measured times
        run_times[i] = elapsed_time

        # Calculate running standard deviation and mean using the Welford algorithm
        w.update(elapsed_time)

        # Enforce time limit (default 5 seconds)
        over_time = perf_counter_ns() > max_time

        # Wait to test whether measurements fall below the target error threshold until a sufficient
        # sample size (30 or more iterations) has been reached.
        below_target_error = (z * (w.std / sqrt(i))) / w.mean <= _TARGET_ERROR if i >= 30 else False

        # Stop looping if the maximum time limit has been reached or if the measurements have fallen
        # below the maximum time limit, and save the reason for exiting early.
        if over_time or below_target_error:
            exited_early = True
            exit_reason = (
                f"Time limit reached ({_TIME_LIMIT} sec.)"
                if over_time
                else f"Target error reached (≤{_TARGET_ERROR:.2%})"
            )
            run_times = run_times[:i]
            break

    # Return logging threshold to previous level
    adjust_log_levels(prev_level)

    # Include the early exit condiiton (if one was met)
    if exited_early:
        run_stats["Exited early"] = exit_reason

    # Report basic stats after converting to an appropriate time scale
    repetitions: int = min([iterations, len(run_times)])
    rel_error: str = (
        f"{((z * (w.std / sqrt(repetitions))) / w.mean):.2%}"
        if repetitions >= 30
        else "N/A (<30 samples)"
    )
    median_times: str = time_from_ns(median(run_times))
    stdev_times: str = time_from_ns(w.std)
    rel_stdev: float = w.std / w.mean
    min_times: str = time_from_ns(min(run_times))
    max_times: str = time_from_ns(max(run_times))
    pct_10: str = time_from_ns(percentile(run_times, q=10))
    pct_90: str = time_from_ns(percentile(run_times, q=90))

    # Dictionary for log table
    run_stats |= {
        "Iterations": f"{repetitions:,} / {iterations:,}",
        "Standard error": rel_error,
        "Confidence": f"{_CONFIDENCE_INTERVAL:.1%}",
        "section_1": "-----",  # Add separator
        "Average": time_from_ns(w.mean),
        "Median": median_times,
        "Stdev": f"±{stdev_times} ({rel_stdev:.2%})",
        "Mid 80%": f"{pct_10} - {pct_90}",
        "Min/Max": f"{min_times} - {max_times}",
    }

    # Report 5 longest iterations if results are not within target error
    if repetitions >= 5 and not below_target_error:
        longest_five: list[str] = [time_from_ns(t) for t in run_times[argsort(-run_times)][:5]]
        run_stats["section_2"] = "-----"  # Add separator
        for i, run in zip(range(5), longest_five):
            place = f"Longest #{i + 1}"
            run_stats[place] = run

    log_table(logger, run_stats, headers=("Metric", "Value"))
    return value, elapsed_time


def stopwatch(
    _func: Callable = None, *, silent: bool = False, iterations: int = 1, profiling: bool = False
) -> Callable:
    """Decorate a function to measure total CPU time.

    Args:
        * _func (Callable, optional): Function to be benchmarked.
        * silent (bool, optional): Measure the function but don't write any log messages. Only
        effective for functions that are not profiled nor measured more than once.
        * iterations (int, optional): Number of times to repeat the function call. Useful for
        evaluating very fast or inconsistent functions, but will limit total execution time to five
        seconds or until the target error threshold (default: 0.05%) is reached, whichever comes
        first. Writes a table with statistics to the debug log. Defaults to 1.
        * profiling (bool, optional): Use cProfile for call-level profiling. Defaults to False.

    Returns:
        * Callable: Returns the passed function.
    """
    def decorator(func: Callable) -> Callable:
        active: bool = logger.level <= 10

        @wraps(func)
        def func_timer(*args, **kwargs) -> Callable:
            # Silently execute the function when logging above debug threshold
            if not active:
                return func(*args, **kwargs)

            # Use built-in profiler if specified
            if profiling:
                return profile_function(func, args, kwargs)

            measurable_func: bool = func.__name__ not in _IGNORED_FUNCS
            repeated: bool = iterations > 1 and measurable_func
            elapsed_time: float = 0.0
            value: Callable  # Contains executed function after profiling

            value, elapsed_time = (
                repeated_measurements(func, args, kwargs, iterations)
                if repeated
                else measure_once(func, silent, *args, **kwargs)
            )

            # Record if measured function exceeded maximum time limit
            if (
                elapsed_time >= (_TIME_LIMIT * 1_000_000_000)
                and measurable_func
                and not running_from_exe()
            ):
                logger.info(f"{func.__name__} took longer than {_TIME_LIMIT} seconds!")
            return value

        return func_timer

    return decorator if _func is None else decorator(_func)


def time_from_ns(elapsed: float, verbose: bool = True) -> str:
    """Convert a nanosecond measurement into a more meaningful time scale."""
    precision: int
    unit: str

    if elapsed > 0:
        precision = 3
        if elapsed < 1000:
            unit = "ns"
        elif elapsed < 1_000_000:
            elapsed /= 1000
            unit = "us"
        elif elapsed < 1_000_000_000:
            elapsed /= 1_000_000
            unit = "ms"
        elif elapsed < 60_000_000_000:
            elapsed /= 1_000_000_000
            unit = "sec"
            precision = 2
        elif elapsed < 36_000_000_000_000:
            elapsed /= 60_000_000_000
            unit = "min"
            precision = 1
        else:
            elapsed /= 36_000_000_000_000
            unit = "hr"
            precision = 1
        return f"{elapsed:,.{precision}f} {unit}"
    return "happened too quickly to measure!" if verbose else "N/A"


class Welford:
    """Lightweight algorithm for calculating mean and variance in a single pass."""

    __slots__ = ("_num", "_sum", "_mean", "_var", "_min", "_max")

    def __init__(self) -> None:
        self._num: int = 0
        self._sum: float = 0.0
        self._mean: float = 0.0
        self._var: float = 0.0
        self._min: float
        self._max: float

    def update(self, value: float) -> None:
        """Compute the new count, mean, and variance."""
        self._num += 1
        self._sum += value
        self._min = min([value, self._min]) if hasattr(self, "_min") else value
        self._max = max([value, self._max]) if hasattr(self, "_max") else value

        new_mean = self._mean + (value - self._mean) / self._num
        new_var = self._var + (value - self._mean) * (value - new_mean)

        self._mean = new_mean
        self._var = new_var

    @property
    def num(self) -> float:
        return self._num

    @property
    def sum(self) -> float:
        return self._sum

    @property
    def mean(self) -> float:
        return self._mean

    @property
    def min(self) -> float:
        return self._min

    @property
    def max(self) -> float:
        return self._max

    @property
    def std(self) -> float:
        return 0 if self._num == 1 else sqrt(self._var / (self._num - 1))
