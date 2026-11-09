"""Small example of using SISO-REF-010 from an application."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from siso_ref010 import EntityType, SisoRef010API

DEFAULT_VERSION = 37
DEFAULT_CODE = "1.2.225.1.3.3.4"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--standard-version", type=int, default=DEFAULT_VERSION)
    parser.add_argument("--entity-type", default=DEFAULT_CODE, help="Seven numeric fields separated by dots")
    args = parser.parse_args(argv)

    try:
        api = SisoRef010API.bundled(args.standard_version)
        entity_type = EntityType.from_string(args.entity_type)
        explanation = api.explain_entity(entity_type)
    except (TypeError, ValueError) as exc:
        parser.error(str(exc))

    resolution = explanation.resolution
    print(f"Edition: {api.info().data_version}")
    print(f"Code: {entity_type}")
    print(f"Resolution: {resolution.human_outcome} ({resolution.status.value})")
    if explanation.qualified_description:
        print(f"Matched hierarchy: {explanation.qualified_description}")
    if resolution.unspecified_components:
        print(f"Unspecified fields: {', '.join(resolution.unspecified_components)}")
    if resolution.unresolved_components:
        print(f"Unresolved fields: {', '.join(resolution.unresolved_components)}")
    print(f"Entity Type bytes: {entity_type.to_bytes().hex()} (8 bytes, not a complete PDU)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
