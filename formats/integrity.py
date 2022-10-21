"""Class for representing a file's integrity based on data inclusions and quality."""

from enum import Enum


class Integrity(Enum):
    """Symbols for file grade and status."""

    # Pre-validation states
    Initialized = (-2, "Base file object has been created.")
    Pending = (-1, "File is being processed.")
    # Valid states
    Ideal = (0, "File appears to be in good health.")
    Dirty = (1, "Minor accuracy or integrity issues.")
    Partial = (
        2,
        "A key data field (e.g., frame times, elapsed time) is missing, empty, or fully zeroed.",
    )
    Mangled = (
        3,
        """Potentially major accuracy or integrity issues, such as zeros in the frame time data or a
        inspection violation. See below for details.""",
    )
    # Invalid states
    Invalid = (
        99,
        "File not available for plotting or statistics but may be inspected in the File Viewer tab.",
    )

    def id(self) -> int:
        """Return the numerical integrity value."""
        return self.value[0]

    def description(self) -> str:
        """Return the integrity state's description."""
        return self.value[1]

    def valid(self) -> bool:
        """Return a boolean indicating if the file has been loaded and contains sufficient data."""
        return 0 <= self.id() < 99
