import argparse
import re
from collections import deque
from configparser import ConfigParser, SectionProxy
from copy import deepcopy
from dataclasses import dataclass
from importlib.metadata import Distribution
from io import StringIO
from itertools import chain
from typing import (
    IO,
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)

import tomli
import tomli_w
from packaging.requirements import Requirement
from packaging.specifiers import Specifier, SpecifierSet
from packaging.version import Version
from packaging.version import parse as parse_version

from ._utilities import (
    ConfigurationFileType,
    get_configuration_file_type,
    get_installed_distributions,
    is_requirement_string,
    iter_distinct,
    iter_find_requirements_lists,
    iter_parse_delimited_values,
    normalize_name,
)


@dataclass
class _Version:
    """
    Instances of this class can be be passed as `self` in a call
    to `packaging.version.Version.__str__`, and thereby can facilitate
    operations to mimic mutability for the aforementioned class.
    """

    epoch: int
    release: Tuple[int, ...]
    pre: Any
    post: Any
    dev: Any
    local: Any


def _update_requirement_specifiers(
    requirement: Requirement, installed_version_string: str
) -> None:
    """
    This function updates specifier version numbers for a requirement
    to match the installed version of the package
    """
    installed_version: Version = parse_version(installed_version_string)
    specifier: Specifier
    updated_specifier_strings: List[str] = []
    for specifier in requirement.specifier:  # type: ignore
        # Only update requirement to match our installed version
        # if the requirement is *inclusive*
        if ("=" in specifier.operator) and ("!" not in specifier.operator):
            specifier_version: Version = parse_version(specifier.version)
            assert installed_version.release is not None
            if specifier_version.release is None:
                updated_specifier_strings.append(f"{specifier.operator}")
            else:
                greater_or_equal_specificity: bool = len(
                    specifier_version.release
                ) >= len(installed_version.release)
                specifier_version_data: _Version = _Version(
                    epoch=installed_version.epoch,
                    # Truncate the updated version requirement at the same
                    # level of specificity as the old
                    release=installed_version.release[
                        : len(specifier_version.release)
                    ],
                    pre=(
                        installed_version.pre
                        if greater_or_equal_specificity
                        else None
                    ),
                    post=(
                        installed_version.post
                        if greater_or_equal_specificity
                        else None
                    ),
                    dev=(
                        installed_version.dev
                        if greater_or_equal_specificity
                        else None
                    ),
                    local=(
                        installed_version.local
                        if greater_or_equal_specificity
                        else None
                    ),
                )
                version_string: str = Version.__str__(
                    specifier_version_data  # type: ignore
                )
                updated_specifier_strings.append(
                    f"{specifier.operator}{version_string}"
                )
        else:
            updated_specifier_strings.append(str(specifier))
    requirement.specifier = SpecifierSet(",".join(updated_specifier_strings))


def _get_updated_requirement_string(
    requirement_string: str, ignore: Set[str]
) -> str:
    """
    This function updates version numbers in a requirement string to match
    those installed in the current environment
    """
    # Skip empty requirement strings
    if not is_requirement_string(requirement_string):
        return requirement_string
    requirement: Requirement = Requirement(requirement_string)
    name: str = normalize_name(requirement.name)
    if name in ignore:
        return requirement_string
    try:
        distribution: Distribution = get_installed_distributions()[name]
        _update_requirement_specifiers(requirement, distribution.version)
    except KeyError:
        # If the requirement isn't installed, we can't update the version
        pass
    return str(requirement)


def _normalize_ignore_argument(ignore: Iterable[str]) -> Set[str]:
    ignore_set: Set[str]
    # Normalize/harmonize excluded project names
    if isinstance(ignore, str):
        ignore = (ignore,)
    ignore_set = set(map(normalize_name, ignore))
    return ignore_set


def _get_updated_requirements_txt(
    data: str, ignore: Iterable[str] = ()
) -> str:
    """
    Return the contents of a *requirements.txt* file, updated to reflect the
    currently installed project versions, excluding those specified in
    `ignore`.

    Parameters:

    - data (str): The contents of a *requirements.txt* file
    - ignore ([str]): One or more project names to leave as-is
    """
    ignore_set: Set[str] = _normalize_ignore_argument(ignore)

    def get_updated_requirement_string(requirement: str) -> str:
        return _get_updated_requirement_string(requirement, ignore=ignore_set)

    return "\n".join(map(get_updated_requirement_string, data.split("\n")))


def _get_updated_setup_cfg(
    data: str, ignore: Iterable[str] = (), all_extra_name: str = ""
) -> str:
    """
    Return the contents of a *setup.cfg* file, updated to reflect the
    currently installed project versions, excluding those specified in
    `ignore`.

    Parameters:

    - data (str): The contents of a *setup.cfg* file
    - ignore ([str]): One or more project names to leave as-is
    - all_extra_name (str): An (optional) extra name which will
      consolidate requirements from all other extras
    """
    ignore_set: Set[str] = _normalize_ignore_argument(ignore)

    def get_updated_requirement_string(requirement: str) -> str:
        return _get_updated_requirement_string(requirement, ignore=ignore_set)

    # Parse
    parser: ConfigParser = ConfigParser()
    parser.read_string(data)
    # Update
    if ("options" in parser) and ("install_requires" in parser["options"]):
        parser["options"]["install_requires"] = "\n".join(
            map(  # type: ignore
                get_updated_requirement_string,
                parser["options"]["install_requires"].split("\n"),
            )
        )
    if "options.extras_require" in parser:
        extras_require: SectionProxy = parser["options.extras_require"]
        all_extra_requirements: List[str] = []
        extra_name: str
        extra_requirements_string: str
        extra_requirements: List[str]
        for extra_name, extra_requirements_string in extras_require.items():
            if extra_name != all_extra_name:
                extra_requirements = list(
                    map(
                        get_updated_requirement_string,
                        extra_requirements_string.split("\n"),
                    )
                )
                if all_extra_name:
                    all_extra_requirements += extra_requirements
                extras_require[extra_name] = "\n".join(extra_requirements)
        # If a name was specified for an all-encompasing extra,
        # we de-duplicate and update or create that extra
        if all_extra_name:
            # We pre-pend an empty requirement string in order to]
            # force new-line creation at the beginning of the extra
            extras_require[all_extra_name] = "\n".join(
                iter_distinct([""] + all_extra_requirements)
            )
    # Return as a string
    setup_cfg: str
    setup_cfg_io: IO[str]
    with StringIO() as setup_cfg_io:
        parser.write(setup_cfg_io)
        setup_cfg_io.seek(0)
        setup_cfg = re.sub(r"[ ]+(\n|$)", r"\1", setup_cfg_io.read()).strip()
        return f"{setup_cfg}\n"


def _get_updated_tox_ini(data: str, ignore: Iterable[str] = ()) -> str:
    """
    Return the contents of a **tox.ini** file, updated to reflect the
    currently installed project versions, excluding those specified in
    `ignore`.

    Parameters:

    - data (str): The contents of a **tox.ini** file
    - ignore ([str]): One or more project names to leave as-is
    """
    ignore_set: Set[str] = _normalize_ignore_argument(ignore)

    def get_updated_requirement_string(requirement: str) -> str:
        prefix: Optional[str] = None
        if ":" in requirement:
            prefix, requirement = requirement.split(":", maxsplit=1)
        requirement = _get_updated_requirement_string(
            requirement, ignore=ignore_set
        )
        if prefix is not None:
            requirement = f"{prefix}: {requirement.lstrip()}"
        return requirement

    # Parse
    parser: ConfigParser = ConfigParser()
    parser.read_string(data)

    def update_section_options(section_name: str, option_name: str) -> None:
        if parser.has_option(section_name, option_name):
            parser.set(
                section_name,
                option_name,
                "\n".join(
                    map(
                        get_updated_requirement_string,
                        parser.get(section_name, option_name).split("\n"),
                    )
                ),
            )

    def update_section(section_name: str) -> None:
        update_section_options(section_name, "deps")
        if section_name == "tox":
            update_section_options(section_name, "requires")

    # Update
    list(map(update_section, parser.sections()))
    # Return as a string
    tox_ini: str
    tox_ini_io: IO[str]
    with StringIO() as tox_ini_io:
        parser.write(tox_ini_io)
        tox_ini_io.seek(0)
        tox_ini = re.sub(r"[ ]+(\n|$)", r"\1", tox_ini_io.read()).strip()
        return f"{tox_ini}\n"


def _update_document_requirements(
    document: Dict[str, Any],
    ignore: Iterable[str] = (),
    include_pointers: Tuple[str, ...] = (),
    exclude_pointers: Tuple[str, ...] = (),
) -> None:
    ignore_set: Set[str] = _normalize_ignore_argument(ignore)

    def get_updated_requirement_string(requirement: str) -> str:
        return _get_updated_requirement_string(requirement, ignore=ignore_set)

    # Find and update requirements
    requirements_list: List[str]
    for requirements_list in iter_find_requirements_lists(
        document,
        include_pointers=include_pointers,
        exclude_pointers=exclude_pointers,
    ):
        requirements_list[:] = list(
            map(
                get_updated_requirement_string,
                requirements_list,
            )
        )


def _get_updated_pyproject_toml(
    data: str,
    ignore: Iterable[str] = (),
    all_extra_name: str = "",
    include_pointers: Tuple[str, ...] = (),
    exclude_pointers: Tuple[str, ...] = (),
) -> str:
    """
    Return the contents of a *pyproject.toml* file, updated to reflect the
    currently installed project versions, excluding those specified in
    `ignore`.

    Parameters:
        data: The contents of a *pyproject.toml* file
        ignore: One or more project names to leave as-is
        all_extra_name: An (optional) extra name which will
            consolidate requirements from all other extras
        include_pointers: A tuple of JSON pointers indicating elements to
            include (defaults to all elements).
        exclude_pointers: A tuple of JSON pointers indicating elements to
            exclude (defaults to no exclusions).

    Returns:
        The contents of the updated pyproject.toml file.
    """
    # Parse pyproject.toml
    original_pyproject: Dict[str, Any] = tomli.loads(data)
    updated_pyproject: Dict[str, Any] = deepcopy(original_pyproject)
    # Find and update requirements
    _update_document_requirements(
        updated_pyproject,
        ignore=ignore,
        include_pointers=include_pointers,
        exclude_pointers=exclude_pointers,
    )
    # Update consolidated optional requirements
    project_optional_dependencies: Dict[str, List[str]] = (
        updated_pyproject.get("project", {}).get("optional-dependencies", {})
    )
    # Update an extra indicated to encompass all other extras
    if project_optional_dependencies and all_extra_name:
        key: str
        dependencies: List[str]
        project_optional_dependencies[all_extra_name] = list(
            iter_distinct(
                chain(
                    *(
                        dependencies
                        for key, dependencies in (
                            project_optional_dependencies.items()
                        )
                        if key != all_extra_name
                    )
                )
            )
        )
    # Only dump the data if something was updated
    if original_pyproject != updated_pyproject:
        return tomli_w.dumps(updated_pyproject)
    return data


def _get_updated_toml(
    data: str,
    ignore: Iterable[str] = (),
    include_pointers: Tuple[str, ...] = (),
    exclude_pointers: Tuple[str, ...] = (),
) -> str:
    """
    Return the contents of a TOML file, updated to reflect the
    currently installed project versions, excluding those specified in
    `ignore`.

    Note: This functions identically to `get_updated_pyproject_toml`, but
    does not consolidate optional dependencies.

    Parameters:
        data: The contents of a TOML file
        ignore: One or more package names to leave as-is
        include_pointers: A tuple of JSON pointers indicating elements to
            include (defaults to all elements).
        exclude_pointers: A tuple of JSON pointers indicating elements to
            exclude (defaults to no exclusions).

    Returns:
        The contents of the updated TOML file.
    """
    # Parse pyproject.toml
    original_pyproject: Dict[str, Any] = tomli.loads(data)
    updated_pyproject: Dict[str, Any] = deepcopy(original_pyproject)
    # Find and update requirements
    _update_document_requirements(
        updated_pyproject,
        ignore=ignore,
        include_pointers=include_pointers,
        exclude_pointers=exclude_pointers,
    )
    # Only dump the data if something was updated
    if original_pyproject != updated_pyproject:
        return tomli_w.dumps(updated_pyproject)
    return data


def _update(
    path: str,
    ignore: Iterable[str] = (),
    all_extra_name: str = "",
    include_pointers: Tuple[str, ...] = (),
    exclude_pointers: Tuple[str, ...] = (),
) -> None:
    data: str
    update_function: Callable[[str], str]
    kwargs: Dict[str, Union[str, Iterable[str]]] = {}
    configuration_file_type: ConfigurationFileType = (
        get_configuration_file_type(path)
    )
    if configuration_file_type == ConfigurationFileType.SETUP_CFG:
        update_function = _get_updated_setup_cfg
        if all_extra_name:
            kwargs["all_extra_name"] = all_extra_name
    elif configuration_file_type == ConfigurationFileType.PYPROJECT_TOML:
        update_function = _get_updated_pyproject_toml
        kwargs.update(
            all_extra_name=all_extra_name,
            include_pointers=include_pointers,
            exclude_pointers=exclude_pointers,
        )
    elif configuration_file_type == ConfigurationFileType.TOML:
        update_function = _get_updated_toml
        kwargs.update(
            include_pointers=include_pointers,
            exclude_pointers=exclude_pointers,
        )
    elif configuration_file_type == ConfigurationFileType.TOX_INI:
        update_function = _get_updated_tox_ini
    elif configuration_file_type == ConfigurationFileType.REQUIREMENTS_TXT:
        update_function = _get_updated_requirements_txt
    else:
        raise NotImplementedError(
            f"Updating requirements for {path} is not supported"
        )
    kwargs["ignore"] = ignore
    file_io: IO[str]
    with open(path) as file_io:
        data = file_io.read()
    updated_data: str = update_function(data, **kwargs)
    if updated_data == data:
        print(f"All requirements were already up-to-date in {path}")
    else:
        print(f"Updating requirements in {path}")
        with open(path, "w") as file_io:
            file_io.write(updated_data)


def update(
    paths: Iterable[str],
    ignore: Iterable[str] = (),
    all_extra_name: str = "",
    include_pointers: Tuple[str, ...] = (),
    exclude_pointers: Tuple[str, ...] = (),
) -> None:
    """
    Update requirement versions in the specified files.

    Parameters:
        path: One or more local paths to a setup.cfg,
            setup.cfg, and/or requirements.txt files
        ignore: One or more project names to ignore (leave as-is)
        all_extra_name: If provided, an extra which consolidates
            the requirements for all other extras will be added/updated to
            setup.cfg or setup.cfg (this argument is ignored for
            requirements.txt files)
        include_pointers: A tuple of JSON pointers indicating elements to
            include (defaults to all elements).
        exclude_pointers: A tuple of JSON pointers indicating elements to
            exclude (defaults to no exclusions).
    """
    if isinstance(paths, str):
        paths = (paths,)

    def update_(path: str) -> None:
        _update(
            path,
            ignore=ignore,
            all_extra_name=all_extra_name,
            include_pointers=include_pointers,
            exclude_pointers=exclude_pointers,
        )

    deque(map(update_, paths), maxlen=0)


def main() -> None:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="dependence update",
        description=(
            "Update requirement versions in the specified files "
            "to align with currently installed versions of each distribution."
        ),
    )
    parser.add_argument(
        "-i",
        "--ignore",
        default=[],
        type=str,
        action="append",
        help=(
            "A comma-separated list of distributions to ignore (leave "
            "any requirements pertaining to the package as-is) "
        ),
    )
    parser.add_argument(
        "-aen",
        "--all-extra-name",
        default="",
        type=str,
        help=(
            "If provided, an extra which consolidates the requirements "
            "for all other extras will be added/updated to pyproject.toml "
            "or setup.cfg (this argument is ignored for "
            "requirements.txt files and other TOML files)"
        ),
    )
    parser.add_argument(
        "--include-pointer",
        default=[],
        type=str,
        action="append",
        help=(
            "One or more JSON pointers of elements to *include* "
            "(applies to TOML files only)"
        ),
    )
    parser.add_argument(
        "--exclude-pointer",
        default=[],
        type=str,
        action="append",
        help=(
            "One or more JSON pointers of elements to *exclude* "
            "(applies to TOML files only)"
        ),
    )
    parser.add_argument(
        "path",
        nargs="+",
        type=str,
        help=(
            "One or more local paths to a *.toml, setup.cfg, "
            "and/or requirements.txt file"
        ),
    )
    namespace: argparse.Namespace = parser.parse_args()
    update(
        paths=namespace.path,
        ignore=tuple(iter_parse_delimited_values(namespace.ignore)),
        all_extra_name=namespace.all_extra_name,
        include_pointers=tuple(namespace.include_pointer),
        exclude_pointers=tuple(namespace.exclude_pointer),
    )


if __name__ == "__main__":
    main()
