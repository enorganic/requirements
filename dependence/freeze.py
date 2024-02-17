import argparse
from fnmatch import fnmatch
from itertools import chain
from typing import Iterable, Set, Tuple

import importlib_metadata
from more_itertools import unique_everseen

from ._utilities import iter_parse_delimited_values
from .utilities import (
    get_distribution,
    get_required_distribution_names,
    get_requirement_string_distribution_name,
    install_requirement,
    is_configuration_file,
    iter_configuration_file_requirement_strings,
    normalize_name,
)

_DO_NOT_PIN_DISTRIBUTION_NAMES: Set[str] = {
    # standard library
    "importlib-metadata",
    "importlib-resources",
}


def get_frozen_requirements(
    requirements: Iterable[str] = (),
    exclude: Iterable[str] = (),
    exclude_recursive: Iterable[str] = (),
    no_version: Iterable[str] = (),
) -> Tuple[str, ...]:
    """
    Get the (frozen) requirements for one or more specified distributions or
    configuration files.

    Parameters:

    - requirements ([str]): One or more requirement specifiers (for example:
      "requirement-name[extra-a,extra-b]" or ".[extra-a, extra-b]) and/or paths
      to a setup.cfg, pyproject.toml, tox.ini or requirements.txt file
    - exclude ([str]): One or more distributions to exclude/ignore
    - exclude_recursive ([str]): One or more distributions to exclude/ignore.
      Note: Excluding a distribution here excludes all requirements which would
      be identified through recursively.
      those requirements occur elsewhere.
    - no_version ([str]) = (): Exclude version numbers from the output
      (only return distribution names)
    """
    # Separate requirement strings from requirement files
    if isinstance(requirements, str):
        requirements = {requirements}
    else:
        requirements = set(requirements)
    if isinstance(no_version, str):
        no_version = (no_version,)
    elif not isinstance(no_version, tuple):
        no_version = tuple(no_version)
    requirement_files: Set[str] = set(
        filter(is_configuration_file, requirements)
    )
    requirement_strings: Set[str] = requirements - requirement_files
    name: str
    return tuple(
        sorted(
            _iter_frozen_requirements(
                unique_everseen(
                    chain(
                        requirement_strings,
                        *map(
                            iter_configuration_file_requirement_strings,
                            requirement_files,
                        ),
                    )
                ),
                exclude=set(
                    chain(
                        # Exclude requirement strings which are *not*
                        # distribution names (such as editable package paths),
                        # as in these cases we are typically looking for this
                        # package's dependencies
                        (
                            set(
                                map(
                                    get_requirement_string_distribution_name,
                                    requirement_strings,
                                )
                            )
                            - set(map(normalize_name, requirement_strings))
                        ),
                        map(normalize_name, exclude),
                    )
                ),
                exclude_recursive=set(map(normalize_name, exclude_recursive)),
                no_version=no_version,
            ),
            key=lambda name: name.lower(),
        )
    )


def _iter_frozen_requirements(
    requirement_strings: Iterable[str],
    exclude: Set[str],
    exclude_recursive: Set[str],
    no_version: Iterable[str] = (),
) -> Iterable[str]:
    def get_requirement_string(distribution_name: str) -> str:
        def distribution_name_matches_pattern(pattern: str) -> bool:
            return fnmatch(distribution_name, pattern)

        # * Don't pin importlib-metadata, as it is part of the standard
        #   library so we should use the version distributed with
        #   python, and...
        # * Only include the version in the requirement string if
        #   the package name does not match any patterns provided in the
        #   `no_version` argument
        if (distribution_name in _DO_NOT_PIN_DISTRIBUTION_NAMES) or any(
            map(distribution_name_matches_pattern, no_version)
        ):
            return distribution_name
        distribution: importlib_metadata.Distribution
        try:
            distribution = get_distribution(distribution_name)
        except importlib_metadata.PackageNotFoundError:
            # If the distribution is missing, install it
            install_requirement(distribution_name, echo=False)
            distribution = importlib_metadata.distribution(distribution_name)
        return f"{distribution.name}=={distribution.version}"

    def get_required_distribution_names_(requirement_string: str) -> Set[str]:
        name: str = get_requirement_string_distribution_name(
            requirement_string
        )
        if name in exclude_recursive:
            return set()
        return (
            get_required_distribution_names(
                requirement_string, exclude=exclude_recursive
            )
            | {name}
        ) - exclude

    requirements: Iterable[str] = unique_everseen(
        chain(*map(get_required_distribution_names_, requirement_strings)),
    )

    requirements = map(get_requirement_string, requirements)
    return requirements


def freeze(
    requirements: Iterable[str] = (),
    exclude: Iterable[str] = (),
    exclude_recursive: Iterable[str] = (),
    no_version: Iterable[str] = (),
) -> None:
    """
    Print the (frozen) requirements for one or more specified requirements or
    configuration files.

    Parameters:

    - requirements ([str]): One or more requirement specifiers (for example:
      "requirement-name[extra-a,extra-b]" or ".[extra-a, extra-b]) and/or paths
      to a setup.py, setup.cfg, pyproject.toml, tox.ini or requirements.txt
      file
    - exclude ([str]): One or more distributions to exclude/ignore
    - exclude_recursive ([str]): One or more distributions to exclude/ignore.
      Note: Excluding a distribution here excludes all requirements which would
      be identified through recursively.
      those requirements occur elsewhere.
    - no_version ([str]) = (): Exclude version numbers from the output
      (only print distribution names) for package names matching any of these
      patterns
    """
    print(
        "\n".join(
            get_frozen_requirements(
                requirements=requirements,
                exclude=exclude,
                exclude_recursive=exclude_recursive,
                no_version=no_version,
            )
        )
    )


def main() -> None:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="dependence freeze",
        description=(
            "This command prints dependencies inferred from an installed "
            "distribution or project, in a similar format to the "
            "output of `pip freeze`, except that all generated requirements "
            'are specified in the format "distribution-name==0.0.0" '
            "(including for editable installations). Using this command "
            "instead of `pip freeze` to generate requirement files ensures "
            "that you don't bloat your requirements files with superfluous "
            "distributions."
        ),
    )
    parser.add_argument(
        "requirement",
        nargs="+",
        type=str,
        help=(
            "One or more requirement specifiers (for example: "
            '"requirement-name", "requirement-name[extra-a,extra-b]", '
            '".[extra-a, extra-b]" or '
            '"../other-editable-package-directory[extra-a, extra-b]) '
            "and/or paths to a setup.py, setup.cfg, pyproject.toml, "
            "tox.ini or requirements.txt file"
        ),
    )
    parser.add_argument(
        "-e",
        "--exclude",
        default=[],
        type=str,
        action="append",
        help=(
            "A distribution (or comma-separated list of distributions) to "
            "exclude from the output"
        ),
    )
    parser.add_argument(
        "-er",
        "--exclude-recursive",
        default=[],
        type=str,
        action="append",
        help=(
            "A distribution (or comma-separated list of distributions) to "
            "exclude from the output. Unlike -e / --exclude, "
            "this argument also precludes recursive requirement discovery "
            "for the specified packages, thereby excluding all of the "
            "excluded package's requirements which are not required by "
            "another (non-excluded) distribution."
        ),
    )
    parser.add_argument(
        "-nv",
        "--no-version",
        type=str,
        default=[],
        action="append",
        help=(
            "Don't include versions (only output distribution names) "
            "for packages matching this/these glob pattern(s) (note: the "
            "value must be single-quoted if it contains wildcards)"
        ),
    )
    arguments: argparse.Namespace = parser.parse_args()
    freeze(
        requirements=arguments.requirement,
        exclude=tuple(iter_parse_delimited_values(arguments.exclude)),
        exclude_recursive=tuple(
            iter_parse_delimited_values(arguments.exclude_recursive)
        ),
        no_version=arguments.no_version,
    )


if __name__ == "__main__":
    main()
