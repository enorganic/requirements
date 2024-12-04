import sys
from importlib import import_module
from types import ModuleType

from . import __name__ as _module_name
from ._utilities import get_exception_text


def _print_help() -> None:
    print(
        "Usage:\n"
        "  dependence <command> [options]\n\n"
        "Commands:\n"
        "  update                      Update requirement versions in the "
        "specified\n"
        "                              files to align with currently installed"
        " versions\n"
        "                              of each distribution\n"
        "  freeze                      Print dependencies inferred from an "
        "installed\n"
        "                              distribution or project, in a similar "
        "format\n"
        "                              to the output of `pip freeze`."
    )


def _get_command() -> str:
    command: str = ""
    if len(sys.argv) > 1:
        command = sys.argv.pop(1).lower().replace("-", "_")
    return command


def main() -> None:
    """
    Run a sub-module `main` function.
    """
    command = _get_command()
    if command in ("__help", "_h"):
        _print_help()
        return
    module: ModuleType
    try:
        try:
            module = import_module(f"{_module_name}.{command}.__main__")
        except ImportError:
            module = import_module(f"{_module_name}.{command}")
        module.main()  # type: ignore
    except ImportError:
        print(get_exception_text())
        _print_help()


if __name__ == "__main__":
    main()
