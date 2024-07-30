import sys
from functools import lru_cache
from itertools import chain
from subprocess import DEVNULL
from subprocess import check_output as _check_output
from traceback import format_exception
from typing import Any, Dict, Hashable, Iterable, List, Set, Tuple

import tomli


def check_output(command: Tuple[str, ...]) -> str:
    """
    This function wraps `subprocess.check_output`, but redirects stderr
    to a temporary file, then deletes that file (a platform-independent
    means of redirecting output to DEVNULL).

    Parameters:

    - command (Tuple[str, ...]): The command to run
    """
    return _check_output(command, stderr=DEVNULL, text=True)


def iter_distinct(items: Iterable[Hashable]) -> Iterable:
    """
    Yield distinct elements, preserving order
    """
    visited: Set[Hashable] = set()
    item: Hashable
    for item in items:
        if item not in visited:
            visited.add(item)
            yield item


@lru_cache()
def pyproject_toml_defines_project(pyproject_toml_path: str) -> bool:
    pyproject: Dict[str, Any]
    try:
        with open(pyproject_toml_path, "r") as pyproject_io:
            pyproject = tomli.loads(pyproject_io.read())
    except FileNotFoundError:
        return False
    return bool(pyproject.get("project", {}).get("name"))


def get_exception_text() -> str:
    """
    When called within an exception, this function returns a text
    representation of the error matching what is found in
    `traceback.print_exception`, but is returned as a string value rather than
    printing.
    """
    return "".join(format_exception(*sys.exc_info()))


def append_exception_text(error: Exception, message: str) -> None:
    """
    Cause `message` to be appended to an error's exception text.
    """
    last_attribute_name: str
    for last_attribute_name in ("strerror", "msg"):
        last_attribute_value = getattr(error, last_attribute_name, "")
        if last_attribute_value:
            setattr(
                error, last_attribute_name, f"{last_attribute_value}{message}"
            )
            break
    if not last_attribute_value:
        index: int
        arg: Any
        reversed_args: List[Any] = list(reversed(error.args)) or [""]
        for index, value in enumerate(reversed_args):
            if isinstance(value, str):
                reversed_args[index] = f"{value}{message}"
                break
        error.args = tuple(reversed(reversed_args))


def _iter_parse_delimited_value(value: str, delimiter: str) -> Iterable[str]:
    return value.split(delimiter)


def iter_parse_delimited_values(
    values: Iterable[str], delimiter: str = ","
) -> Iterable[str]:
    """
    This function iterates over input values which have been provided as a
    list or iterable and/or a single string of character-delimited values.
    A typical use-case is parsing multi-value command-line arguments.
    """
    if isinstance(values, str):
        values = (values,)

    def iter_parse_delimited_value_(value: str) -> Iterable[str]:
        return _iter_parse_delimited_value(value, delimiter=delimiter)

    return chain(*map(iter_parse_delimited_value_, values))
