"""Collection of color shades associated with major GPU vendors."""

from random import choice

from core.configuration import session, setting
from core.logger import get_logger, log_exception
from core.utilities import vendor_gpu_substrings
from numpy import random as nprand

from gui.metadata import read_record, record_exists

logger = get_logger(__name__)

_RNG = nprand.default_rng()
_VENDOR_SUBSTRINGS = vendor_gpu_substrings()
_NVIDIA: tuple = (
    (173, 213, 102),
    (159, 206, 77),
    (145, 199, 51),
    (132, 192, 25),
    (118, 185, 0),  # Base color
    (106, 167, 0),
    (94, 148, 0),
    (83, 130, 0),
    (71, 111, 0),
    (59, 93, 0),
    (47, 74, 0),
)

_AMD: tuple = (
    (235, 102, 131),
    (231, 77, 111),
    (228, 51, 90),
    (224, 25, 70),
    (221, 0, 49),  # Base color
    (199, 0, 44),
    (177, 0, 39),
    (155, 0, 34),
    (133, 0, 29),
    (111, 0, 25),
    (88, 0, 20),
)

_INTEL: tuple = (
    (113, 176, 218),
    (89, 163, 212),
    (65, 150, 205),
    (42, 137, 199),
    (18, 124, 193),  # Base color
    (16, 112, 174),
    (14, 99, 154),
    (13, 87, 135),
    (11, 74, 116),
    (9, 62, 97),
    (7, 50, 77),
)


def current_alpha() -> int:
    """Return the default alpha value based on current file selection."""
    return int(
        setting(
            "Plotting", "NormalAlpha" if session("SelectedFilePath") == "" else "DiminishedAlpha"
        )
    )


def clamp_to_8bpcc(color: int) -> int:
    """Keep an RGB component clamped between 0 and 255."""
    return int(max(0, min(color, 255)))


def adjust_alpha(rgba: tuple, factor: float) -> tuple:
    """Return an RGBA tuple with a modified alpha component."""
    try:
        if len(rgba) == 3:
            return rgba
        return rgba[:3] + (clamp_to_8bpcc(rgba[3] * factor),)
    except Exception as e:
        log_exception(logger, e, "Failed to adjust color components")
        return rgba


def adjust_luminance(rgba: tuple, factor: float) -> tuple:
    """Return an RGBA tuple with modified RGB components."""
    try:
        return tuple(clamp_to_8bpcc(color * factor) for color in rgba[:3])
    except Exception as e:
        log_exception(logger, e, "Failed to adjust color components")
        return rgba


def random_pen_color() -> tuple[int, int, int, int]:
    """Return a random RGBA quadruplet."""
    return (_RNG.integers(192), _RNG.integers(192), _RNG.integers(192), current_alpha())


def restore_color(path: str) -> tuple[int, int, int, int]:
    """Read and verify a stored color to use for plotting."""
    color = random_pen_color()

    try:
        if record_exists(path, "Color"):
            rgb: dict = read_record(path, "Color")
            r: int = clamp_to_8bpcc(rgb["R"])
            g: int = clamp_to_8bpcc(rgb["G"])
            b: int = clamp_to_8bpcc(rgb["B"])
            color = (r, g, b, current_alpha())
    except Exception as e:
        log_exception(logger, e, "Failed to restore color metadata")
    finally:
        return color


def vendor_color(gpu_name: str) -> tuple[int, int, int, int]:
    """Return a generic or vendor-aligned RGBA tuple for a valid capture file."""
    # Lend some transparency to improve legibility of overlapping plots
    alpha: int = current_alpha()
    gpu_name = gpu_name.upper()

    if any(s in gpu_name for s in _VENDOR_SUBSTRINGS["NVIDIA"]):
        return choice(_NVIDIA) + (alpha,)
    elif any(s in gpu_name for s in _VENDOR_SUBSTRINGS["AMD"]):
        return choice(_AMD) + (alpha,)
    elif any(s in gpu_name for s in _VENDOR_SUBSTRINGS["INTEL"]):
        return choice(_INTEL) + (alpha,)
    return random_pen_color()
