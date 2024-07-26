import argparse
from fnmatch import fnmatch
from importlib.metadata import Distribution
from importlib.metadata import distribution as _get_distribution
from itertools import chain
from typing import Dict, Iterable, MutableSet, Optional, Tuple, cast

from ._utilities import iter_distinct, iter_parse_delimited_values
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


def _iter_sort_dependents_last(requirements: Iterable[str]) -> Iterable[str]:
    """
    Sort requirements such that dependents are first and dependencies are last.
    """
    requirements = list(requirements)
    distribution_name: str
    distribution_requirement: Dict[str, str] = {
        get_requirement_string_distribution_name(requirement): requirement
        for requirement in requirements
    }
    dependent_dependencies: Dict[str, MutableSet[str]] = {
        distribution_name: get_required_distribution_names(requirement)
        for distribution_name, requirement in distribution_requirement.items()
    }
    while dependent_dependencies:
        dependent: str
        dependencies: MutableSet[str]
        item: Tuple[str, MutableSet[str]]
        for dependent, dependencies in sorted(
            tuple(dependent_dependencies.items()),
            key=lambda item: item[0].lower(),
        ):

            def is_non_circular_requirement(dependency: str) -> bool:
                """
                Return `True` if the dependency is still among the unaccounted
                for requirements, and is not a circular reference
                """
                return (dependency in dependent_dependencies) and (
                    # Exclude interdependent distributions
                    # (circular references)
                    dependent
                    not in dependent_dependencies[dependency]
                )

            if (not dependencies) or not any(
                map(
                    is_non_circular_requirement,
                    dependencies,
                )
            ):
                yield distribution_requirement.pop(dependent)
                del dependent_dependencies[dependent]


def get_frozen_requirements(
    requirements: Iterable[str] = (),
    exclude: Iterable[str] = (),
    exclude_recursive: Iterable[str] = (),
    no_version: Iterable[str] = (),
    dependency_order: bool = False,
    reverse: bool = False,
    depth: Optional[int] = None,
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
    - dependency_order (bool) = False: Sort requirements so that dependents
      precede dependencies
    - depth (int|None) = None: Depth of recursive requirement discovery
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
    frozen_requirements: Iterable[str] = iter_distinct(
        chain(
            requirement_strings,
            *map(
                iter_configuration_file_requirement_strings,
                requirement_files,
            ),
        )
    )
    if depth is not None:
        depth -= 1
    if (depth is None) or depth >= 0:
        frozen_requirements = _iter_frozen_requirements(
            frozen_requirements,
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
            depth=depth,
        )
    if dependency_order:
        frozen_requirements = tuple(
            _iter_sort_dependents_last(frozen_requirements)
        )
        if not reverse:
            frozen_requirements = tuple(reversed(frozen_requirements))
    else:
        name: str
        frozen_requirements = tuple(
            sorted(
                frozen_requirements,
                key=lambda name: name.lower(),
                reverse=reverse,
            )
        )
    return frozen_requirements


def _iter_frozen_requirements(
    requirement_strings: Iterable[str],
    exclude: MutableSet[str],
    exclude_recursive: MutableSet[str],
    no_version: Iterable[str] = (),
    depth: Optional[int] = None,
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
        depth_: Optional[int] = None,
    ) -> MutableSet[str]:
        name: str = get_requirement_string_distribution_name(
            requirement_string
        )
        if name in exclude_recursive:
            return set()
        distribution_names: MutableSet[str] = {name}
        if (depth_ is None) or depth_:
            distribution_names |= get_required_distribution_names(
                requirement_string,
                exclude=exclude_recursive,
                depth=None if (depth_ is None) else depth_ - 1,
            )
        return cast(
            MutableSet[str],
            distribution_names - exclude,
        )

    distribution_names: MutableSet[str]
    requirements: Iterable[str] = iter_distinct(
        chain(
            *map(
                lambda distribution_names: get_required_distribution_names_(
                    distribution_names, None if (depth is None) else depth - 1
                ),
                requirement_strings,
            )
        ),
    )
    requirements = map(get_requirement_string, requirements)
    return requirements


def freeze(
    requirements: Iterable[str] = (),
    exclude: Iterable[str] = (),
    exclude_recursive: Iterable[str] = (),
    no_version: Iterable[str] = (),
    dependency_order: bool = False,
    reverse: bool = False,
    depth: Optional[int] = None,
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
    - dependency_order (bool) = False: Sort requirements so that dependents
      precede dependencies
    - depth (int|None) = None: Depth of recursive requirement discovery
    """
    print(
        "\n".join(
            get_frozen_requirements(
                requirements=requirements,
                exclude=exclude,
                exclude_recursive=exclude_recursive,
                no_version=no_version,
                dependency_order=dependency_order,
                reverse=reverse,
                depth=depth,
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
    parser.add_argument(
        "-do",
        "--dependency-order",
        default=False,
        action="store_true",
        help="Sort requirements so that dependents precede dependencies",
    )
    parser.add_argument(
        "--reverse",
        default=False,
        action="store_true",
        help="Print requirements in reverse order",
    )
    parser.add_argument(
        "-d",
        "--depth",
        default=None,
        type=int,
        help="Depth of recursive requirement discovery",
    )
    namespace: argparse.Namespace = parser.parse_args()
    freeze(
        requirements=namespace.requirement,
        exclude=tuple(iter_parse_delimited_values(namespace.exclude)),
        exclude_recursive=tuple(
            iter_parse_delimited_values(namespace.exclude_recursive)
        ),
        no_version=namespace.no_version,
        dependency_order=namespace.dependency_order,
        depth=namespace.depth,
    )


if __name__ == "__main__":
    main()
