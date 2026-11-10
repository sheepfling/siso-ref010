"""Smoke-check the first and latest bundled SISO editions."""

from __future__ import annotations

from siso_ref010 import Collection, SisoRef010API
from siso_ref010.catalog import BUNDLED_STANDARD_VERSIONS


def _check_version(version: int) -> None:
    api = SisoRef010API.bundled(version)
    info = api.info()
    if info.data_version is None or f"v{version}" not in info.data_version.lower():
        raise ValueError(f"v{version}: edition metadata does not match the requested version")

    summary = api.inspector.summary()
    if summary.enumeration_tables == 0 or summary.entity_values == 0:
        raise ValueError(f"v{version}: expected enumeration and entity records")
    if summary.unresolved_entity_values:
        raise ValueError(f"v{version}: found {summary.unresolved_entity_values} unresolved entity rows")

    countries = api.choices(Collection.COUNTRIES)
    search = api.search("", limit=1)
    if not countries.items or search.total == 0 or not search.hits:
        raise ValueError(f"v{version}: expected country choices and searchable entity records")
    print(
        f"OK v{version}: countries={len(countries.items)}, "
        f"tables={summary.enumeration_tables}, entity_values={summary.entity_values}"
    )


def main() -> int:
    """Load, inspect, and query the oldest and newest bundled editions."""

    if not BUNDLED_STANDARD_VERSIONS:
        raise SystemExit("At least one bundled edition is required for endpoint checks")
    versions = (min(BUNDLED_STANDARD_VERSIONS), max(BUNDLED_STANDARD_VERSIONS))
    failures = 0
    for version in versions:
        try:
            _check_version(version)
        except Exception as error:
            failures += 1
            print(f"FAIL v{version}: {type(error).__name__}: {error}")
    print(f"Checked {len(versions)} endpoint editions; failures={failures}")
    return int(failures != 0)


if __name__ == "__main__":
    raise SystemExit(main())
