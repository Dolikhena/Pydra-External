"""This module creates, reads, and updates a local database for custom capture file metadata."""


from json import dumps, load
from pathlib import Path
from time import time

from core.configuration import setting
from core.logger import get_logger, log_exception

logger = get_logger(__name__)

_EXPIRATION_TIME: int = int(setting("Metadata", "ExpirationTime")) * 86_400
_STORAGE_DISABLED: bool = _EXPIRATION_TIME == 0
_FILE_PATH: Path = Path("metadata.json").resolve()
_STORAGE: dict

# Read current metadata file or create an empty dict if it does not exist
if _STORAGE_DISABLED or not _FILE_PATH.exists():
    _STORAGE = {}
else:
    try:
        with open(_FILE_PATH) as metadata_file:
            _STORAGE = load(metadata_file)

        # Purge old records
        current_time: int = int(time())
        _STORAGE = {
            k: v
            for k, v in _STORAGE.items()
            if (current_time - v["Record"]["Last Accessed"]) <= _EXPIRATION_TIME
        }
    except Exception as e:
        log_exception(logger, e, "Failed to read metadata file")
        _STORAGE = {}


def record_exists(file_hash: str, section: str) -> bool:
    """Return a bool indicating that a record-section pair exists in the current metadata."""
    return (
        not _STORAGE_DISABLED
        and file_hash in _STORAGE
        and section in _STORAGE[file_hash]
        and _STORAGE[file_hash][section]
    )


def read_record(file_hash: str, section: str = "Properties") -> dict:
    """Return the capture file's stored metadata, if any exists.."""
    if not record_exists(file_hash, section):
        return {}

    current_time = int(time())
    _STORAGE[file_hash]["Record"].update({"Last Accessed": current_time})
    return _STORAGE[file_hash][section]


def update_record(file_hash: str, properties: dict, section: str = "Properties") -> None:
    """Create or update the record for a capture file."""
    if _STORAGE_DISABLED:
        return

    current_time = int(time())
    record_data = {"Record": {"Last Updated": current_time, "Last Accessed": current_time}}

    if file_hash not in _STORAGE:
        _STORAGE[file_hash] = {**record_data, section: {**properties}}
    else:
        _STORAGE[file_hash].update(**record_data)
        if section in _STORAGE[file_hash]:
            _STORAGE[file_hash][section].update(**properties)
        else:
            _STORAGE[file_hash][section] = properties


def update_metadata_file() -> None:
    """Write the updated dict to a file when closing down."""
    if _STORAGE_DISABLED or not _STORAGE:
        return remove_all_records()

    try:
        with open(_FILE_PATH, "w") as metadata_file:
            metadata_file.write(dumps(_STORAGE, indent=4, separators=(",", ": ")))
    except Exception as e:
        log_exception(logger, e, "Failed to write metadata file")


def remove_record(file_hash: str, section: str = "Properties") -> None:
    """Remove a section from a record or the whole record if it will be empty apart from expiry data."""
    if not record_exists(file_hash, section):
        return

    _STORAGE[file_hash].pop(section)
    if len(_STORAGE[file_hash].keys()) > 1:
        _STORAGE[file_hash]["Record"].update({"Last Updated": int(time())})
    else:
        _STORAGE.pop(file_hash)


def remove_section(section: str) -> None:
    """Remove the passed section from all stored records, then update the file."""
    if not _STORAGE:
        return

    for record in list(_STORAGE):
        remove_record(record, section)
    update_metadata_file()


def remove_all_records() -> None:
    """Remove all records from the file."""
    if _FILE_PATH.exists():
        Path.unlink(_FILE_PATH)
        _STORAGE.clear()
