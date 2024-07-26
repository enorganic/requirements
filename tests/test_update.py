from collections import deque
from configparser import ConfigParser
from pathlib import Path
from typing import Iterable

import pytest
import tomli
from packaging.requirements import Requirement
from packaging.specifiers import Specifier
from packaging.version import Version

from dependence.update import (
    get_updated_pyproject_toml,
    get_updated_requirements_txt,
    get_updated_setup_cfg,
)

TEST_PROJECT_A: Path = (
    Path(__file__).absolute().parent.joinpath("test_projects/test_project_a/")
)
TEST_PROJECT_B: Path = (
    Path(__file__).absolute().parent.joinpath("test_projects/test_project_b/")
)
TEST_PROJECT_C: Path = (
    Path(__file__).absolute().parent.joinpath("test_projects/test_project_c/")
)


def is_nonzero(value: int) -> bool:
    return isinstance(value, int) and value != 0


def is_zero(value: int) -> bool:
    return isinstance(value, int) and value == 0


def validate_nonzero_specifier(specifier: Specifier) -> None:
    # Ensure this release version is not 0, 0.0, 0.0.0, etc.
    assert any(map(is_nonzero, Version(specifier.version).release)), str(
        specifier
    )


def validate_zero_specifier(specifier: Specifier) -> None:
    # Ensure this release version is not 0, 0.0, 0.0.0, etc.
    assert all(map(is_zero, Version(specifier.version).release)), str(
        specifier
    )


def validate_requirement(requirement_string: str) -> None:
    print(requirement_string)
    if requirement_string:
        print(requirement_string)
        requirement: Requirement = Requirement(requirement_string)
        if requirement.name in ("pip", "setuptools"):
            deque(
                map(
                    validate_zero_specifier,  # type: ignore
                    requirement.specifier,
                ),
                maxlen=0,
            )
        else:
            deque(
                map(
                    validate_nonzero_specifier,  # type: ignore
                    requirement.specifier,
                ),
                maxlen=0,
            )


def validate_requirements(requirements: Iterable[str]) -> None:
    if isinstance(requirements, str):
        requirements = requirements.split("\n")
    list(map(validate_requirement, requirements))


def test_get_updated_setup_cfg() -> None:
    """
    Ensure that updating a setup.cfg file occurs without problems
    """
    setup_cfg_path: Path = TEST_PROJECT_A.joinpath("setup.cfg")
    updated_setup_cfg_data: str
    with open(setup_cfg_path) as setup_cfg_io:
        setup_cfg_data: str = setup_cfg_io.read()
        # Update versions for all packages *except* pip
        print(setup_cfg_data)
        updated_setup_cfg_data = get_updated_setup_cfg(
            setup_cfg_data,
            ignore=("pip", "setuptools"),
            all_extra_name="all",
        )
        print(
            f"{str(setup_cfg_path).strip()}\n\n"
            "Before:\n\n"
            f"{setup_cfg_data.strip()}\n\n"
            "After:\n\n"
            f"{updated_setup_cfg_data.strip()}\n"
        )
        assert updated_setup_cfg_data != setup_cfg_data
    # Ensure all versions are updated to a non-zero release number
    parser: ConfigParser = ConfigParser()
    parser.read_string(updated_setup_cfg_data)
    validate_requirements(parser["options"]["install_requires"])
    extra_requirements_string: str
    for extra_requirements_string in parser["options.extras_require"].values():
        validate_requirements(extra_requirements_string)


def test_get_updated_pyproject_toml_a() -> None:
    """
    Ensure that updating a pyproject.toml file occurs without problems
    """
    pyproject_toml_path: Path = TEST_PROJECT_A.joinpath("pyproject.toml")
    updated_pyproject_toml_data: str
    with open(pyproject_toml_path) as pyproject_toml_io:
        pyproject_toml_data: str = pyproject_toml_io.read()
        # Update versions for all packages *except* pip
        updated_pyproject_toml_data = get_updated_pyproject_toml(
            pyproject_toml_data,
            ignore=("pip", "setuptools"),
        )
        print(
            f"{str(pyproject_toml_path).strip()}\n\n"
            "Before:\n\n"
            f"{pyproject_toml_data.strip()}\n\n"
            "After:\n\n"
            f"{updated_pyproject_toml_data.strip()}\n"
        )
        assert updated_pyproject_toml_data != pyproject_toml_data
    # Ensure all versions are updated to a non-zero release number
    validate_requirements(
        tomli.loads(updated_pyproject_toml_data)["build-system"]["requires"]
    )


def test_get_updated_pyproject_toml_b() -> None:
    """
    Ensure that updating a pyproject.toml file occurs without problems
    """
    pyproject_toml_path: Path = TEST_PROJECT_B.joinpath("pyproject.toml")
    updated_pyproject_toml_data: str
    with open(pyproject_toml_path) as pyproject_toml_io:
        pyproject_toml_data: str = pyproject_toml_io.read()
        # Update versions for all packages *except* pip
        updated_pyproject_toml_data = get_updated_pyproject_toml(
            pyproject_toml_data,
            ignore=("pip", "setuptools"),
        )
        print(
            f"{str(pyproject_toml_path).strip()}\n\n"
            "Before:\n\n"
            f"{pyproject_toml_data.strip()}\n\n"
            "After:\n\n"
            f"{updated_pyproject_toml_data.strip()}\n"
        )
        assert updated_pyproject_toml_data != pyproject_toml_data
    # Ensure all versions are updated to a non-zero release number
    validate_requirements(
        tomli.loads(updated_pyproject_toml_data)["build-system"]["requires"]
        + tomli.loads(updated_pyproject_toml_data)["project"]["dependencies"]
        + tomli.loads(updated_pyproject_toml_data)["project"][
            "optional-dependencies"
        ]["twine"]
        + tomli.loads(updated_pyproject_toml_data)["project"][
            "optional-dependencies"
        ]["wheel"]
    )


def test_get_updated_requirements_txt() -> None:
    """
    Ensure that updating a setup.cfg file occurs without problems
    """
    project: Path
    for project in (TEST_PROJECT_A, TEST_PROJECT_B):
        requirements_txt_path: Path = project.joinpath("requirements.txt")
        with open(requirements_txt_path) as requirements_txt_io:
            requirements_txt_data: str = requirements_txt_io.read()
            updated_requirements_txt_data: str = get_updated_requirements_txt(
                requirements_txt_data, ignore=("pip", "setuptools")
            )
            print(
                f"{str(requirements_txt_path).strip()}\n\n"
                "Before:\n\n"
                f"{requirements_txt_data.strip()}\n\n"
                "After:\n\n"
                f"{updated_requirements_txt_data.strip()}\n"
            )
            assert updated_requirements_txt_data != requirements_txt_data
            validate_requirements(updated_requirements_txt_data)


if __name__ == "__main__":
    pytest.main()
