"""Architectural boundary enforcement tests.

Conforms to docs/ARCHITECTURE.md §4, §5 and AGENTS.md §5.
Enforces that apps/fuel has zero Django/ORM/HTTP imports and dependency directions hold.
"""

import ast
from pathlib import Path

APPS_DIR = Path(__file__).resolve().parent.parent.parent / "apps"


def get_imports(py_file: Path) -> list[str]:
    """Parse a Python source file into a list of imported module names."""
    tree = ast.parse(py_file.read_text(), filename=str(py_file))
    imported_modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_modules.append(node.module)
    return imported_modules


def test_apps_fuel_has_zero_django_orm_http_imports():
    """apps/fuel domain layer must remain pure Python/NumPy with zero framework dependencies."""
    fuel_dir = APPS_DIR / "fuel"
    forbidden_prefixes = (
        "django",
        "rest_framework",
        "httpx",
        "urllib",
        "requests",
        "apps.geo",
        "apps.stations",
        "apps.weather",
        "apps.planner",
    )

    for py_file in fuel_dir.glob("*.py"):
        # Django's apps.py is the only permitted framework entrypoint
        if py_file.name == "apps.py":
            continue

        imported = get_imports(py_file)
        for mod in imported:
            for forbidden in forbidden_prefixes:
                assert not mod.startswith(forbidden), (
                    f"Forbidden import '{mod}' found in {py_file.name}. "
                    f"apps/fuel must not import framework, ORM, or higher layers."
                )


def test_apps_common_has_no_app_dependencies():
    """apps/common must only contain foundation utilities and never import from feature apps."""
    common_dir = APPS_DIR / "common"
    forbidden_prefixes = (
        "apps.fuel",
        "apps.geo",
        "apps.stations",
        "apps.weather",
        "apps.planner",
    )

    for py_file in common_dir.glob("*.py"):
        if py_file.name == "apps.py":
            continue
        imported = get_imports(py_file)
        for mod in imported:
            for forbidden in forbidden_prefixes:
                assert not mod.startswith(forbidden), (
                    f"Forbidden import '{mod}' found in common/{py_file.name}."
                )


def test_geo_and_stations_do_not_import_higher_layers():
    """apps/geo and apps/stations must not import planner or fuel logic."""
    for app_name in ("geo", "stations"):
        app_dir = APPS_DIR / app_name
        forbidden_prefixes = ("apps.planner", "apps.weather")
        for py_file in app_dir.rglob("*.py"):
            if py_file.name == "apps.py":
                continue
            imported = get_imports(py_file)
            for mod in imported:
                for forbidden in forbidden_prefixes:
                    assert not mod.startswith(forbidden), (
                        f"Forbidden import '{mod}' found in {app_name}/{py_file.name}."
                    )
