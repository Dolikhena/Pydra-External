"""Collection of functions used explicitly for development."""

from gc import get_referents
from inspect import getmembers, isfunction, signature, stack
from pprint import pformat
from sys import getsizeof
from typing import Any, Callable

from core.logger import get_logger
from core.utilities import size_from_bytes

logger = get_logger(__name__)


def deep_object_inspection(inspected_object: Any) -> None:
    """Print the cumulative memory allocation for an object, its references, and attributes."""
    objects: list = [inspected_object]
    memory_alloc: int = 0
    ids: set = set()
    refs: list

    while objects:
        refs = []
        linked_objects = (obj for obj in objects if id(obj) not in ids)

        for obj in linked_objects:
            ids.add(id(obj))
            memory_alloc += getsizeof(obj)
            refs.append(obj)

        objects = get_referents(*refs)

    obj_name: str = inspected_object.__class__.__name__
    total_size: str = size_from_bytes(memory_alloc)
    logger.debug(
        pformat(
            f"{obj_name} contained {len(ids):,} objects totaling {memory_alloc:,} bytes ({total_size})"
        )
    )


def get_function_caller() -> None:
    """Print the caller of a function."""
    call_stack: str = ""
    func_name: str = ""

    for _ in stack():
        func_name = _[3]
        if func_name in ("<module>", "main"):
            break
        elif func_name in (
            "get_function_caller",
            "measure_once",
            "repeated_measurements",
            "func_timer",
        ):
            continue
        else:
            call_stack += f"{func_name} <- "

    if call_stack:
        logger.debug(call_stack[:-4])


def get_function_members(func: Callable) -> None:
    """Print the members of a function."""
    logger.debug(pformat(f"{func.__qualname__} members: {getmembers(func, isfunction)}"))


def get_function_signature(func: Callable) -> None:
    """Print the signature of a function."""
    logger.debug(pformat(f"{func.__qualname__} signature: {signature(func)}"))
