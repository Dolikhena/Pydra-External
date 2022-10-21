"""A collection of custom exceptions for various Pydra modules."""

from core.logger import get_logger

logger = get_logger(__name__)


# Custom exceptions
class FileIntegrityError(Exception):
    """Raised when parsing capture files with integrity or inclusion issues."""

    def __init__(self, message: str) -> None:
        """Log the message passed with this exception."""
        logger.error(message)


class IrregularStructureError(Exception):
    """Raised when parsing capture files with inconsistent row widths."""

    def __init__(self, message: str) -> None:
        """Log the message passed with this exception."""
        logger.error(message)
