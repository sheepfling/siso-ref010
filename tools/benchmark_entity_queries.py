"""Compare indexed entity queries with a full source-record scan."""

from __future__ import annotations

import argparse
from statistics import median
from time import perf_counter

from dis_entity_types import EditionValue, EntityTypeAPI

_FIELD_NAMES = ("entity_kind", "domain", "country", "category", "subcategory", "specific", "extra")


def _matches(row: EditionValue, fields: tuple[int | None, ...], text: str | None) -> bool:
    codes = row.hierarchy_codes
    for index, requested in enumerate(fields):
        if requested is None:
            continue
        if index < len(codes):
            actual = codes[index]
            if actual != requested and not (index == 2 and actual == 0 and requested != 0):
                return False
        elif not (
            index == len(codes)
            and row.value_min is not None
            and row.value_max is not None
            and row.value_min <= requested <= row.value_max
        ):
            return False
    if text:
        searchable = " ".join(
            (
                row.description or "",
                *row.path,
                *(str(code) for code in codes),
                *(str(code) for code in (row.value, row.value_min, row.value_max) if code is not None),
            )
        ).casefold()
        if text.casefold() not in searchable:
            return False
    return True


def _scan_total(rows: tuple[EditionValue, ...], fields: tuple[int | None, ...], text: str | None) -> int:
    return sum(_matches(row, fields, text) for row in rows)


def _indexed_total(api: EntityTypeAPI, fields: tuple[int | None, ...], text: str | None) -> int:
    return api.query_entities(
        entity_kind=fields[0],
        domain=fields[1],
        country=fields[2],
        category=fields[3],
        subcategory=fields[4],
        specific=fields[5],
        extra=fields[6],
        text=text,
        limit=0,
    ).total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", type=int, default=37, help="Bundled edition to query (default: 37)")
    parser.add_argument("--iterations", type=int, default=100, help="Warm queries per case (default: 100)")
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be positive")

    start = perf_counter()
    one_off_api = EntityTypeAPI.bundled(args.version)
    construction_ms = (perf_counter() - start) * 1000
    cached_start = perf_counter()
    api = EntityTypeAPI.bundled(args.version)
    cached_construction_ms = (perf_counter() - cached_start) * 1000
    one_off_start = perf_counter()
    one_off = one_off_api.query_entities(country=153, text="Tromp", limit=20)
    one_off_ms = (perf_counter() - one_off_start) * 1000
    warmup_start = perf_counter()
    warmup = api.warmup()
    warmup_ms = (perf_counter() - warmup_start) * 1000
    rows = api.inspector.entity_values()

    cases = (
        ((None, None, 153, None, None, None, None), None),
        ((1, None, 153, 6, None, None, None), None),
        ((None, None, 153, None, None, None, None), "Tromp"),
    )
    print(f"edition v{args.version}: {len(rows):,} source entity records")
    print(f"API construction plus catalog projection: {construction_ms:.3f} ms")
    print(f"another API instance from the process cache: {cached_construction_ms:.3f} ms")
    print(f"first one-off query without warmup: {one_off_ms:.3f} ms ({one_off.total} matches)")
    print(f"explicit query-backend warmup: {warmup_ms:.3f} ms ({warmup.indexed_records or 0:,} indexed rows)")
    for fields, text in cases:
        filter_labels = [
            f"{name}={value}" for name, value in zip(_FIELD_NAMES, fields, strict=True) if value is not None
        ]
        if text is not None:
            filter_labels.append(f"text={text!r}")
        indexed_times: list[float] = []
        scan_times: list[float] = []
        indexed_total = 0
        scan_total = 0
        for _ in range(args.iterations):
            started = perf_counter()
            indexed_total = _indexed_total(api, fields, text)
            indexed_times.append((perf_counter() - started) * 1000)
            started = perf_counter()
            scan_total = _scan_total(rows, fields, text)
            scan_times.append((perf_counter() - started) * 1000)
        print(
            f"filters={', '.join(filter_labels)}: indexed median {median(indexed_times):.3f} ms; "
            f"full scan median {median(scan_times):.3f} ms; "
            f"matches indexed/scan={indexed_total}/{scan_total}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
