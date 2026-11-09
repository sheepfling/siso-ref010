"""Backend contract and indexed in-memory execution for entity queries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import NamedTuple, Protocol

from .inspection import (
    EditionInspector,
    EditionValue,
    EditionValueKind,
    _edition_value,  # pyright: ignore[reportPrivateUsage]
    _walk_entity_records,  # pyright: ignore[reportPrivateUsage]
)
from .models.standard import EntityTypeStandard


class EntityFieldFilters(NamedTuple):
    """Optional entity-code filters in DIS hierarchy order."""

    entity_kind: int | None
    domain: int | None
    country: int | None
    category: int | None
    subcategory: int | None
    specific: int | None
    extra: int | None


class EntityQueryRequest(NamedTuple):
    """Backend-neutral entity query fields and page selection."""

    entity_kind: int | None
    domain: int | None
    country: int | None
    category: int | None
    subcategory: int | None
    specific: int | None
    extra: int | None
    text: str | None
    limit: int | None
    offset: int

    @property
    def fields(self) -> EntityFieldFilters:
        return EntityFieldFilters(
            entity_kind=self.entity_kind,
            domain=self.domain,
            country=self.country,
            category=self.category,
            subcategory=self.subcategory,
            specific=self.specific,
            extra=self.extra,
        )


@dataclass(frozen=True, slots=True)
class EntityQueryPage:
    """Total match count and the requested page of source entity records."""

    total: int
    values: tuple[EditionValue, ...]


class EntityQueryBackend(Protocol):
    """Execution boundary for filtering source entity records in one edition."""

    def warmup(self, inspector: EditionInspector) -> int | None:
        """Prepare query indexes and optionally report indexed source-row count."""
        ...

    def query(self, inspector: EditionInspector, request: EntityQueryRequest) -> EntityQueryPage:
        """Return matching source rows in stable source order for the selected edition."""
        ...


class MappingEntityQueryBackend:
    """In-memory backend using inverted code-field indexes and source-order IDs."""

    def __init__(self) -> None:
        self._standard: EntityTypeStandard | None = None
        self._values: tuple[EditionValue, ...] = ()
        self._field_postings: tuple[Mapping[int, frozenset[int]], ...] = ()
        self._ranges_by_depth: tuple[tuple[tuple[int, int, int], ...], ...] = ()
        self._searchable: tuple[str, ...] = ()
        self._last_query: tuple[EntityTypeStandard, EntityQueryRequest, EntityQueryPage] | None = None

    def _index(self, inspector: EditionInspector) -> int:
        standard = inspector.standard
        if self._standard is standard:
            return len(self._values)

        values = inspector.entity_values()
        postings: list[dict[int, set[int]]] = [{} for _ in range(7)]
        ranges: list[list[tuple[int, int, int]]] = [[] for _ in range(7)]
        searchable: list[str] = []
        for record_id, value in enumerate(values):
            codes = value.hierarchy_codes
            for field_index, code in enumerate(codes):
                postings[field_index].setdefault(code, set()).add(record_id)
            if value.value_min is not None and value.value_max is not None:
                range_depth = len(codes)
                if range_depth < len(ranges):
                    ranges[range_depth].append((value.value_min, value.value_max, record_id))
            searchable.append(
                " ".join(
                    (
                        value.description or "",
                        *value.path,
                        *(str(code) for code in codes),
                        *(
                            str(code)
                            for code in (value.value, value.value_min, value.value_max)
                            if code is not None
                        ),
                    )
                ).casefold()
            )

        self._standard = standard
        self._values = values
        self._field_postings = tuple(
            {value: frozenset(ids) for value, ids in field.items()} for field in postings
        )
        self._ranges_by_depth = tuple(tuple(field_ranges) for field_ranges in ranges)
        self._searchable = tuple(searchable)
        return len(values)

    def warmup(self, inspector: EditionInspector) -> int:
        """Build the selected edition's entity rows and field indexes now."""
        return self._index(inspector)

    @classmethod
    def _scan(cls, inspector: EditionInspector, request: EntityQueryRequest) -> EntityQueryPage:
        """Run a one-off query without paying to build reusable indexes."""
        total = 0
        page_values: list[EditionValue] = []
        fields = request.fields
        text = request.text.casefold() if request.text else None
        tables = inspector.standard.enumeration_uid_index
        for branch in inspector.standard.entity_types:
            prefix = (branch.kind, branch.domain, branch.country)
            path = (f"kind {branch.kind}", f"domain {branch.domain}", f"country {branch.country}")
            for entry in branch.categories:
                for row, codes, row_path, table, reference_source in _walk_entity_records(
                    tables, entry, prefix, path
                ):
                    for index, requested in enumerate(fields):
                        if requested is None:
                            continue
                        if index < len(codes):
                            actual = codes[index]
                            if actual != requested and not (index == 2 and actual == 0 and requested != 0):
                                break
                        elif not (
                            index == len(codes)
                            and row.value_min is not None
                            and row.value_max is not None
                            and row.value_min <= requested <= row.value_max
                        ):
                            break
                    else:
                        if text is not None:
                            searchable = " ".join(
                                (
                                    row.description or "",
                                    *row_path,
                                    *(str(code) for code in codes),
                                    *(
                                        str(code)
                                        for code in (row.value, row.value_min, row.value_max)
                                        if code is not None
                                    ),
                                )
                            ).casefold()
                            if text not in searchable:
                                continue
                        if total >= request.offset and (
                            request.limit is None or len(page_values) < request.limit
                        ):
                            page_values.append(
                                _edition_value(
                                    kind=EditionValueKind.ENTITY_TYPE,
                                    entry=row,
                                    path=row_path,
                                    hierarchy_codes=codes,
                                    table=table,
                                    applicability=table.applicability if table is not None else None,
                                    reference_source=reference_source,
                                )
                            )
                        total += 1
        return EntityQueryPage(total=total, values=tuple(page_values))

    def query(self, inspector: EditionInspector, request: EntityQueryRequest) -> EntityQueryPage:
        if self._standard is not inspector.standard:
            cached = self._last_query
            if cached is not None and cached[0] is inspector.standard and cached[1] == request:
                return cached[2]
            page = self._scan(inspector, request)
            self._last_query = (inspector.standard, request, page)
            return page
        self._index(inspector)
        candidate_ids: set[int] | None = None
        for field_index, requested in enumerate(request.fields):
            if requested is None:
                continue
            matches = set(self._field_postings[field_index].get(requested, ()))
            if field_index == 2 and requested != 0:
                matches.update(self._field_postings[field_index].get(0, ()))
            matches.update(
                record_id
                for minimum, maximum, record_id in self._ranges_by_depth[field_index]
                if minimum <= requested <= maximum
            )
            candidate_ids = matches if candidate_ids is None else candidate_ids & matches
            if not candidate_ids:
                break

        selected_ids = range(len(self._values)) if candidate_ids is None else sorted(candidate_ids)
        text = request.text.casefold() if request.text else None
        total = 0
        page_values: list[EditionValue] = []
        for record_id in selected_ids:
            if text is not None and text not in self._searchable[record_id]:
                continue
            if total >= request.offset and (request.limit is None or len(page_values) < request.limit):
                page_values.append(self._values[record_id])
            total += 1
        return EntityQueryPage(total=total, values=tuple(page_values))


__all__ = [
    "EntityFieldFilters",
    "EntityQueryBackend",
    "EntityQueryPage",
    "EntityQueryRequest",
    "MappingEntityQueryBackend",
]
