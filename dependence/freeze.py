import argparse
from fnmatch import fnmatch
from functools import cmp_to_key
from importlib.metadata import Distribution
from importlib.metadata import distribution as _get_distribution
from itertools import chain
from typing import Dict, Iterable, List, MutableSet, Tuple, cast

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

_DO_NOT_PIN_DISTRIBUTION_NAMES: MutableSet[str] = {
    "importlib-metadata",
    "importlib-resources",
}


def _iter_sort_dependents_first(requirements: Iterable[str]) -> Iterable[str]:
    """
    Sort requirements such that dependents are first and dependencies are last.
    """
    requirements = list(requirements)
    dependent_dependencies: Dict[str, MutableSet[str]] = dict(
        (
            get_requirement_string_distribution_name(requirement),
            get_required_distribution_names(requirement),
        )
        for requirement in requirements
    )
    # import sob

    # print(f"!!!{sob.utilities.inspect.represent(dependent_dependencies)}")

    def compare(a: str, b: str) -> int:
        """
        Compare two requirements and return -1 if a < b, 0 if a == b, and 1 if
        a > b.
        """
        distribution_name_a: str = get_requirement_string_distribution_name(a)
        distribution_name_b: str = get_requirement_string_distribution_name(b)
        lowercase_a: str = distribution_name_a.lower()
        lowercase_b: str = distribution_name_b.lower()
        if lowercase_a == lowercase_b:
            return 0
        if distribution_name_b in dependent_dependencies[distribution_name_a]:
            if (
                distribution_name_a
                in dependent_dependencies[distribution_name_b]
            ):
                # the distributions are interdependent, sort alphabetically
                return -1 if lowercase_a < lowercase_b else 1
            # a < b
            return -1
        if distribution_name_a in dependent_dependencies[distribution_name_b]:
            # a > b
            return 1
        # a and b are independent, sort alphabetically
        return -1 if lowercase_a < lowercase_b else 1

    def compare_(a: str, b: str) -> int:
        i: int = compare(a, b)
        if (a, b) == ("iniconfig", "pytest"):
            assert i == 1
        elif (a, b) == ("pytest", "iniconfig"):
            assert i == -1
        return i

    old_requirements: List[str] = list(requirements)
    requirements.sort(key=cmp_to_key(compare_))
    assert old_requirements != requirements
    requirements_str: str = "\n".join(requirements)
    print(f"!!!{requirements_str}")
    yield from requirements


def get_frozen_requirements(
    requirements: Iterable[str] = (),
    exclude: Iterable[str] = (),
    exclude_recursive: Iterable[str] = (),
    no_version: Iterable[str] = (),
    alphabetical_order: bool = False,
    reverse: bool = False,
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
    - alphabetical_order (bool) = False: Sort requirements alphabetically
    """
    # Separate requirement strings from requirement files
    if isinstance(requirements, str):
        requirements = set((requirements,))
    else:
        requirements = set(requirements)
    if isinstance(no_version, str):
        no_version = (no_version,)
    elif not isinstance(no_version, tuple):
        no_version = tuple(no_version)
    requirement_files: MutableSet[str] = set(
        filter(is_configuration_file, requirements)
    )
    requirement_strings: MutableSet[str] = cast(
        MutableSet[str], requirements - requirement_files
    )
    frozen_requirements: Iterable[str] = _iter_frozen_requirements(
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
    )
    if alphabetical_order:
        name: str
        frozen_requirements = tuple(
            sorted(frozen_requirements, key=lambda name: name.lower())
        )
    else:
        frozen_requirements = tuple(
            _iter_sort_dependents_first(frozen_requirements)
        )
        assert frozen_requirements
    if reverse:
        frozen_requirements = tuple(reversed(frozen_requirements))
    return frozen_requirements


def _iter_frozen_requirements(
    requirement_strings: Iterable[str],
    exclude: MutableSet[str],
    exclude_recursive: MutableSet[str],
    no_version: Iterable[str] = (),
) -> Iterable[str]:
    def get_requirement_string(distribution_name: str) -> str:
        def distribution_name_matches_pattern(pattern: str) -> bool:
            return fnmatch(distribution_name, pattern)

        if (distribution_name in _DO_NOT_PIN_DISTRIBUTION_NAMES) or any(
            map(distribution_name_matches_pattern, no_version)
        ):
            return distribution_name
        distribution: Distribution
        try:
            distribution = get_distribution(distribution_name)
        except KeyError:
            # If the distribution is missing, install it
            install_requirement(distribution_name, echo=False)
            distribution = _get_distribution(distribution_name)
        return f"{distribution.metadata['Name']}=={distribution.version}"

    def get_required_distribution_names_(
        requirement_string: str,
    ) -> MutableSet[str]:
        name: str = get_requirement_string_distribution_name(
            requirement_string
        )
        if name in exclude_recursive:
            return set()
        return cast(
            MutableSet[str],
            (
                set((name,))
                | get_required_distribution_names(
                    requirement_string, exclude=exclude_recursive
                )
            )
            - exclude,
        )

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
    alphabetical_order: bool = False,
    reverse: bool = False,
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
    - alphabetical_order (bool) = False: Sort requirements alphabetically
    """
    print(
        "\n".join(
            get_frozen_requirements(
                requirements=requirements,
                exclude=exclude,
                exclude_recursive=exclude_recursive,
                no_version=no_version,
                alphabetical_order=alphabetical_order,
                reverse=reverse,
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
            "distributions. The default sorting starts with directly "
            "specified requirements, followed by recursively discovered "
            "requirements, in the order of discovery."
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
    parser.add_argument(
        "-ao",
        "--alphabetical-order",
        default=False,
        action="store_true",
        help="Print requirements in alphabetical order (case-insensitive)",
    )
    parser.add_argument(
        "--reverse",
        default=False,
        action="store_true",
        help="Print requirements in reverse order",
    )
    arguments: argparse.Namespace = parser.parse_args()
    freeze(
        requirements=arguments.requirement,
        exclude=tuple(iter_parse_delimited_values(arguments.exclude)),
        exclude_recursive=tuple(
            iter_parse_delimited_values(arguments.exclude_recursive)
        ),
        no_version=arguments.no_version,
        alphabetical_order=arguments.alphabetical_order,
    )


if __name__ == "__main__":
    main()
