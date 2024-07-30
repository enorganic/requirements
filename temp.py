from typing import IO, Any, Dict

import tomli

path: str = "tests/test_projects/test_project_c/pyproject.toml"

pyproject_io: IO[str]
with open(path) as pyproject_io:
    pyproject: Dict[str, Any] = tomli.loads(pyproject_io.read())
    print(repr(pyproject))
