"""Pure transformations from the parsed standard to lookup data."""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TypeAlias

from .errors import SisoRef010ValueError
from .models.codes import (
    CategoryCode,
    CountryCode,
    DomainCode,
    EntityFieldCode,
    EntityKey,
    ExtraCode,
    KindCode,
    SpecificCode,
    SubcategoryCode,
)
from .models.entity import create_key
from .models.standard import (
    EntityTypeStandard,
    EnumerationTable,
    EnumerationTableIndex,
    ReferenceEntry,
)


@dataclass(frozen=True, slots=True)
class CatalogRow:
    """One expanded hierarchy entry and the entity fields that contain it."""

    parents: tuple[int, ...]
    value: int
    description: str


@dataclass(frozen=True, slots=True)
class CatalogChild:
    """A selectable child value and its source order beneath one entity prefix."""

    value: EntityFieldCode
    description: str
    source_order: int


ChildrenByPrefix: TypeAlias = Mapping[tuple[EntityFieldCode, ...], tuple[CatalogChild, ...]]


@dataclass(frozen=True, slots=True, weakref_slot=True)
class CatalogData:
    """Immutable lookup projection derived from one parsed SISO standard."""

    standard: EntityTypeStandard | None
    countries: Mapping[CountryCode, str]
    country_rows: tuple[CatalogChild, ...]
    domains: Mapping[tuple[KindCode, DomainCode], str]
    domain_rows: tuple[tuple[KindCode, CatalogChild], ...]
    kinds: Mapping[KindCode, str]
    kind_rows: tuple[CatalogChild, ...]
    categories: Mapping[EntityKey, str]
    subcategories: Mapping[EntityKey, str]
    ambiguous_categories: Mapping[EntityKey, tuple[str, ...]]
    ambiguous_subcategories: Mapping[EntityKey, tuple[str, ...]]
    children_by_prefix: ChildrenByPrefix


def _field_values(expression: str) -> tuple[KindCode, ...]:
    values: list[KindCode] = []
    for part in expression.split(","):
        part = part.strip()
        if not part:
            continue
        bounds: list[int] = []
        for bound in part.split("-"):
            bound = bound.strip()
            if bound.upper() == "X":
                bounds.append(0)
            elif re.fullmatch(r"[0-9]+", bound):
                bounds.append(int(bound))
            else:
                raise SisoRef010ValueError(
                    f"Unsupported SISO applicability value: {bound!r}",
                    code="unsupported_applicability_value",
                    context={"value": bound},
                )
        if len(bounds) == 1:
            values.append(KindCode(bounds[0]))
            continue
        minimum, maximum = bounds[:2]
        if minimum > maximum:
            raise SisoRef010ValueError(
                f"Invalid SISO applicability range: {part!r}",
                code="invalid_applicability_range",
                context={"range": part, "minimum": minimum, "maximum": maximum},
            )
        values.extend(KindCode(value) for value in range(minimum, maximum + 1))
    return tuple(values)


def _applicability_values(value: str | None, field_index: int) -> tuple[KindCode, ...]:
    if not value:
        return ()
    result: list[KindCode] = []
    for expression in value.split(";"):
        fields = expression.strip().split(".")
        if field_index >= len(fields):
            if field_index != 0 or len(fields) != 1:
                continue
            field = fields[0]
        else:
            field = fields[field_index]
        result.extend(_field_values(field))
    return tuple(dict.fromkeys(result))


def _entry_values(entry: ReferenceEntry) -> tuple[int, ...]:
    if entry.value is not None:
        return (entry.value,)
    if entry.value_min is not None and entry.value_max is not None:
        return tuple(range(entry.value_min, entry.value_max + 1))
    return ()


def _key_for_fields(fields: tuple[int, ...]) -> EntityKey:
    return create_key(
        kind=KindCode(fields[0]),
        domain=DomainCode(fields[1]),
        country=CountryCode(fields[2]),
        category=CategoryCode(fields[3]),
        subcategory=SubcategoryCode(fields[4]),
        specific=SpecificCode(fields[5]),
        extra=ExtraCode(fields[6]),
    )


def _prefix_codes(values: tuple[int, ...]) -> tuple[EntityFieldCode, ...]:
    constructors = (
        KindCode,
        DomainCode,
        CountryCode,
        CategoryCode,
        SubcategoryCode,
        SpecificCode,
        ExtraCode,
    )
    return tuple(constructors[index](value) for index, value in enumerate(values))


def _child_code(parent_count: int, value: int) -> EntityFieldCode:
    match parent_count:
        case 3:
            return CategoryCode(value)
        case 4:
            return SubcategoryCode(value)
        case 5:
            return SpecificCode(value)
        case 6:
            return ExtraCode(value)
        case _:
            raise ValueError(f"unsupported entity hierarchy depth: {parent_count}")


def _referenced_tables(
    xref: str | None, enumerations_by_uid: EnumerationTableIndex
) -> tuple[EnumerationTable, ...]:
    try:
        uid = int(xref) if xref is not None else None
    except ValueError:
        uid = None
    tables = enumerations_by_uid.get(uid, ()) if uid is not None else ()
    if not tables:
        raise SisoRef010ValueError(
            f"Unresolved SISO enumeration cross-reference: {xref!r}",
            code="unresolved_enumeration_reference",
            context={"xref": xref},
        )
    return tables


def _walk_entry(
    entry: ReferenceEntry,
    parents: tuple[int, ...],
    enumerations_by_uid: EnumerationTableIndex,
) -> Iterator[CatalogRow]:
    if entry.tag == "subcategory_xref":
        tables = _referenced_tables(entry.source.get("xref"), enumerations_by_uid)
        for table in tables:
            for row in table.entries:
                if row.description is None:
                    continue
                for value in _entry_values(row):
                    yield CatalogRow(parents, value, row.description)
                    next_parents = (*parents, value)
                    for child in entry.children:
                        yield from _walk_entry(child, next_parents, enumerations_by_uid)
        return

    if entry.description is None:
        return
    for value in _entry_values(entry):
        yield CatalogRow(parents, value, entry.description)
        next_parents = (*parents, value)
        for child in entry.children:
            yield from _walk_entry(child, next_parents, enumerations_by_uid)


def _build_enumeration_indexes(
    standard: EntityTypeStandard,
) -> tuple[
    dict[CountryCode, str],
    tuple[CatalogChild, ...],
    dict[tuple[KindCode, DomainCode], str],
    tuple[tuple[KindCode, CatalogChild], ...],
    dict[KindCode, str],
    tuple[CatalogChild, ...],
]:
    countries: dict[CountryCode, str] = {}
    country_rows: list[CatalogChild] = []
    domains: dict[tuple[KindCode, DomainCode], str] = {}
    domain_rows: list[tuple[KindCode, CatalogChild]] = []
    kinds: dict[KindCode, str] = {}
    kind_rows: list[CatalogChild] = []
    for table in standard.enumerations:
        if table.name == "Entity Kind":
            for row in table.entries:
                if row.value is not None and row.description is not None:
                    kinds[KindCode(row.value)] = row.description
                    kind_rows.append(CatalogChild(KindCode(row.value), row.description, len(kind_rows)))
            continue
        if table.name == "Country":
            for row in table.entries:
                if row.value is not None and row.description is not None:
                    countries[CountryCode(row.value)] = row.description
                    country_rows.append(
                        CatalogChild(CountryCode(row.value), row.description, len(country_rows))
                    )
            continue
        if table.name.endswith("Domain"):
            parent_kinds = _applicability_values(table.applicability, 0)
            for row in table.entries:
                if row.value is None or row.description is None:
                    continue
                for kind in parent_kinds:
                    domains[(kind, DomainCode(row.value))] = row.description
                    domain_rows.append(
                        (kind, CatalogChild(DomainCode(row.value), row.description, len(domain_rows)))
                    )
            continue
    return (
        countries,
        tuple(country_rows),
        domains,
        tuple(domain_rows),
        kinds,
        tuple(kind_rows),
    )


def _build_hierarchy_indexes(
    standard: EntityTypeStandard,
) -> tuple[
    dict[EntityKey, str],
    dict[EntityKey, str],
    dict[EntityKey, tuple[str, ...]],
    dict[EntityKey, tuple[str, ...]],
    dict[tuple[EntityFieldCode, ...], list[CatalogChild]],
]:
    categories: dict[EntityKey, str] = {}
    subcategories: dict[EntityKey, str] = {}
    ambiguous_categories: dict[EntityKey, list[str]] = {}
    ambiguous_subcategories: dict[EntityKey, list[str]] = {}
    children_by_prefix: dict[tuple[EntityFieldCode, ...], list[CatalogChild]] = {}
    enumerations_by_uid = standard.enumeration_uid_index
    rows = (
        row
        for branch in standard.entity_types
        for category in branch.categories
        for row in _walk_entry(category, (branch.kind, branch.domain, branch.country), enumerations_by_uid)
    )

    for ordinal, row in enumerate(rows):
        fields = (*row.parents, row.value)
        padded = (*fields, *((0,) * (7 - len(fields))))
        key = _key_for_fields(padded)
        target = categories if len(row.parents) == 3 else subcategories
        ambiguous_target = ambiguous_categories if len(row.parents) == 3 else ambiguous_subcategories
        if key in target:
            ambiguous_target.setdefault(key, [target[key]]).append(row.description)
        target[key] = row.description
        prefix = _prefix_codes(row.parents)
        code = _child_code(len(row.parents), row.value)
        children_by_prefix.setdefault(prefix, []).append(
            CatalogChild(
                value=code,
                description=row.description,
                source_order=ordinal,
            )
        )
    return (
        categories,
        subcategories,
        {key: tuple(descriptions) for key, descriptions in ambiguous_categories.items()},
        {key: tuple(descriptions) for key, descriptions in ambiguous_subcategories.items()},
        children_by_prefix,
    )


def _freeze_children(
    children_by_prefix: Mapping[tuple[EntityFieldCode, ...], list[CatalogChild]],
) -> ChildrenByPrefix:
    return MappingProxyType(
        {parents: tuple(children) for parents, children in children_by_prefix.items()}
    )


def _validated_standard(value: object) -> EntityTypeStandard | None:
    if value is None or isinstance(value, EntityTypeStandard):
        return value
    raise SisoRef010ValueError(
        "catalog data must be parsed from SISO-REF-010 XML",
        code="invalid_catalog_source",
        context={"received_type": type(value).__name__},
    )


def build_catalog_data(standard: EntityTypeStandard | None) -> CatalogData:
    """Project a parsed standard into immutable indexes without mutating the input."""
    standard = _validated_standard(standard)
    if standard is None:
        return CatalogData(
            standard=None,
            countries=MappingProxyType({}),
            country_rows=(),
            domains=MappingProxyType({}),
            domain_rows=(),
            kinds=MappingProxyType({}),
            kind_rows=(),
            categories=MappingProxyType({}),
            subcategories=MappingProxyType({}),
            ambiguous_categories=MappingProxyType({}),
            ambiguous_subcategories=MappingProxyType({}),
            children_by_prefix=MappingProxyType({}),
        )

    countries, country_rows, domains, domain_rows, kinds, kind_rows = _build_enumeration_indexes(standard)
    (
        categories,
        subcategories,
        ambiguous_categories,
        ambiguous_subcategories,
        children_by_prefix,
    ) = _build_hierarchy_indexes(standard)
    return CatalogData(
        standard=standard,
        countries=MappingProxyType(countries),
        country_rows=country_rows,
        domains=MappingProxyType(domains),
        domain_rows=domain_rows,
        kinds=MappingProxyType(kinds),
        kind_rows=kind_rows,
        categories=MappingProxyType(categories),
        subcategories=MappingProxyType(subcategories),
        ambiguous_categories=MappingProxyType(ambiguous_categories),
        ambiguous_subcategories=MappingProxyType(ambiguous_subcategories),
        children_by_prefix=_freeze_children(children_by_prefix),
    )
