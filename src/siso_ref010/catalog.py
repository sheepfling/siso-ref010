"""Read-only lookup operations over a projected SISO-REF-010 catalog."""

from __future__ import annotations

from collections.abc import Callable
from threading import RLock
from typing import cast
from weakref import WeakValueDictionary

from ._paths import PathInput, normalize_path
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
from .models.entity import EntityType, create_key
from .models.standard import EntityTypeStandard
from .parsing.xml import EntityTypeXmlParser
from .projection import CatalogChild, CatalogData, ChildrenByPrefix, build_catalog_data
from .sources import BUNDLED_STANDARD_SOURCE, BundledStandardSource, StandardSource

BUNDLED_STANDARD_VERSIONS = BUNDLED_STANDARD_SOURCE.versions
BUNDLED_STANDARD_VERSION = max(BUNDLED_STANDARD_VERSIONS)


_BUNDLED_CATALOG_DATA_CACHE: WeakValueDictionary[int, CatalogData] = WeakValueDictionary()
_BUNDLED_CATALOG_DATA_CACHE_LOCK = RLock()


def _bundled_catalog_data(version: int) -> CatalogData:
    """Share projections while API instances reference them, without pinning old editions."""
    with _BUNDLED_CATALOG_DATA_CACHE_LOCK:
        cached = _BUNDLED_CATALOG_DATA_CACHE.get(version)
        if cached is not None:
            return cached
        standard = EntityTypeXmlParser.from_bytes(BUNDLED_STANDARD_SOURCE.read_xml(version))
        data = build_catalog_data(standard)
        _BUNDLED_CATALOG_DATA_CACHE[version] = data
        return data


def _children_for(
    children_by_prefix: ChildrenByPrefix,
    parents: tuple[EntityFieldCode, ...],
) -> dict[EntityFieldCode, str]:
    """Return unambiguous children after applying source-ordered country overlay."""
    rows = _choice_rows_for(children_by_prefix, parents)
    grouped: dict[EntityFieldCode, list[str]] = {}
    for row in rows:
        grouped.setdefault(row.value, []).append(row.description)
    for value, descriptions in grouped.items():
        if len(descriptions) > 1:
            raise _ambiguous_choice_error(parents, value, tuple(descriptions))
    return {value: descriptions[0] for value, descriptions in grouped.items()}


def _choice_rows_for(
    children_by_prefix: ChildrenByPrefix,
    parents: tuple[EntityFieldCode, ...],
) -> tuple[CatalogChild, ...]:
    """Overlay country scopes in source order, retaining winner-scope duplicates."""
    specific_rows = tuple(children_by_prefix.get(parents, ()))
    if parents[2] == 0:
        return specific_rows

    generic = (*parents[:2], CountryCode(0), *parents[3:])
    generic_rows = tuple(children_by_prefix.get(generic, ()))
    specific_by_value: dict[EntityFieldCode, list[CatalogChild]] = {}
    generic_by_value: dict[EntityFieldCode, list[CatalogChild]] = {}
    for row in specific_rows:
        specific_by_value.setdefault(row.value, []).append(row)
    for row in generic_rows:
        generic_by_value.setdefault(row.value, []).append(row)

    rows: list[CatalogChild] = []
    for value in specific_by_value.keys() | generic_by_value.keys():
        specific = specific_by_value.get(value, ())
        generic = generic_by_value.get(value, ())
        if specific and generic:
            rows.extend(specific if specific[-1].source_order > generic[-1].source_order else generic)
        else:
            rows.extend(specific or generic)
    return tuple(sorted(rows, key=lambda row: row.source_order))


def _ambiguous_choice_error(
    parents: tuple[EntityFieldCode, ...],
    value: EntityFieldCode,
    descriptions: tuple[str, ...],
) -> SisoRef010ValueError:
    return SisoRef010ValueError(
        f"Entity choice {value} has multiple source descriptions",
        code="ambiguous_entity_choice",
        context={
            "parents": tuple(int(parent) for parent in parents),
            "value": int(value),
            "candidate_descriptions": descriptions,
        },
    )


def _duplicate_descriptions(
    rows: tuple[CatalogChild, ...], key_for: Callable[[CatalogChild], object]
) -> tuple[object, tuple[str, ...]] | None:
    grouped: dict[object, list[str]] = {}
    for row in rows:
        grouped.setdefault(key_for(row), []).append(row.description)
    return next(
        ((key, tuple(descriptions)) for key, descriptions in grouped.items() if len(descriptions) > 1),
        None,
    )


def _raise_ambiguous_enumeration_name(label: str, key: object, descriptions: tuple[str, ...]) -> None:
    raise SisoRef010ValueError(
        f"{label} code {key} has multiple source descriptions",
        code="ambiguous_enumeration_name",
        context={"code": key, "candidate_descriptions": descriptions},
    )


def _child_description_for(
    children_by_prefix: ChildrenByPrefix,
    parents: tuple[EntityFieldCode, ...],
    value: EntityFieldCode,
) -> str | None:
    """Look up one child without failing on ambiguity in a different code."""
    matches = tuple(
        row.description for row in _choice_rows_for(children_by_prefix, parents) if row.value == value
    )
    if len(matches) > 1:
        raise _ambiguous_choice_error(parents, value, matches)
    return matches[0] if matches else None


def _description_for(data: CatalogData, entity: EntityType) -> str:
    fields = entity.as_tuple()
    for depth in range(len(fields), 3, -1):
        parents = fields[: depth - 1]
        value = fields[depth - 1]
        try:
            description = _child_description_for(data.children_by_prefix, parents, value)
        except SisoRef010ValueError as error:
            if error.code != "ambiguous_entity_choice":
                raise
            raise SisoRef010ValueError(
                "Entity code matches multiple source descriptions",
                code="ambiguous_entity_description",
                context={
                    "entity_key": int(entity.to_key(signed=False)),
                    **(error.context or {}),
                },
            ) from error
        if description is not None:
            return description
    return "-"


def _search_descriptions(data: CatalogData, query: str) -> dict[str, tuple[str, ...]]:
    normalized = query.casefold()
    source_rows_by_key: dict[EntityKey, list[tuple[int, str]]] = {}
    for parents, rows in data.children_by_prefix.items():
        for row in rows:
            fields = (*parents, row.value)
            padded = (*fields, *((0,) * (7 - len(fields))))
            key = create_key(
                kind=KindCode(padded[0]),
                domain=DomainCode(padded[1]),
                country=CountryCode(padded[2]),
                category=CategoryCode(padded[3]),
                subcategory=SubcategoryCode(padded[4]),
                specific=SpecificCode(padded[5]),
                extra=ExtraCode(padded[6]),
                signed=False,
            )
            source_rows_by_key.setdefault(key, []).append((len(fields), row.description))

    effective_descriptions: dict[EntityKey, tuple[str, ...]] = {}
    for key, source_rows in source_rows_by_key.items():
        deepest = max(depth for depth, _ in source_rows)
        effective_descriptions[key] = tuple(
            description for depth, description in source_rows if depth == deepest
        )
    return {
        str(EntityType.from_key(key)): descriptions
        for key, descriptions in effective_descriptions.items()
        if any(normalized in description.casefold() for _, description in source_rows_by_key[key])
    }


class ReferenceCatalog:
    """Lookup facade over immutable ``CatalogData`` with small query caches."""

    def __init__(self, standard: EntityTypeStandard | None = None) -> None:
        self._data = build_catalog_data(standard)
        self._children_cache: dict[tuple[EntityFieldCode, ...], dict[EntityFieldCode, str]] = {}
        self._qualified_cache: dict[EntityKey, str] = {}

    @classmethod
    def bundled(cls, version: int | None = None) -> ReferenceCatalog:
        if version is None:
            versions = BUNDLED_STANDARD_SOURCE.versions
            if not versions:
                raise SisoRef010ValueError(
                    "No bundled SISO-REF-010 editions are available",
                    code="no_bundled_editions",
                    context={},
                )
            version = max(versions)
        return cls.from_source(BUNDLED_STANDARD_SOURCE, version)

    @classmethod
    def from_source(cls, source: StandardSource, version: int) -> ReferenceCatalog:
        """Retrieve and parse one edition from a versioned standard source."""
        available = source.versions
        if type(version) is not int or version not in available:
            bundled = isinstance(source, BundledStandardSource)
            raise SisoRef010ValueError(
                f"SISO-REF-010 version {version!r} is unavailable from this source",
                code="unavailable_bundled_version" if bundled else "unavailable_source_version",
                context={"version": version, "available": available},
            )
        if type(source) is BundledStandardSource:
            return cls._from_data(_bundled_catalog_data(version))
        xml = source.read_xml(version)
        standard = EntityTypeXmlParser.from_bytes(xml)
        return cls(standard)

    @classmethod
    def _from_data(cls, data: CatalogData) -> ReferenceCatalog:
        """Create a catalog with shared immutable data and per-instance caches."""
        catalog = cls.__new__(cls)
        catalog._data = data
        catalog._children_cache = {}
        catalog._qualified_cache = {}
        return catalog

    @classmethod
    def from_xml(cls, path: PathInput) -> ReferenceCatalog:
        source = normalize_path(path)
        return cls(EntityTypeXmlParser.from_file(source))

    @property
    def data(self) -> CatalogData:
        """Return the immutable source and index projection used by this catalog."""
        return self._data

    @property
    def standard(self) -> EntityTypeStandard | None:
        """Parsed standard retained as the source for the lookup projection."""
        return self._data.standard

    def initialize(self, standard: EntityTypeStandard) -> None:
        """Replace the projection atomically after successfully building new data."""
        updated = build_catalog_data(standard)
        self._data = updated
        self._children_cache.clear()
        self._qualified_cache.clear()

    @property
    def country_count(self) -> int:
        return len(self._data.countries)

    @property
    def kind_count(self) -> int:
        return len(self._data.kinds)

    @property
    def domain_count(self) -> int:
        return len(self._data.domains)

    @property
    def category_count(self) -> int:
        return len(self._data.categories)

    @property
    def subcategory_count(self) -> int:
        return len(self._data.subcategories)

    def get_all_countries(self) -> dict[CountryCode, str]:
        """Return country names when every numeric code has one source description."""
        duplicates = self._ambiguous_country_names()
        if duplicates:
            code, descriptions = next(iter(duplicates.items()))
            raise SisoRef010ValueError(
                f"Country code {code} has multiple source descriptions",
                code="ambiguous_country_name",
                context={"country": int(code), "candidate_descriptions": descriptions},
            )
        return dict(self._data.countries)

    def get_country_choices(self) -> tuple[CatalogChild, ...]:
        """Return all country source rows, including duplicate-code candidates."""
        return self._data.country_rows

    def get_kind_choices(self) -> tuple[CatalogChild, ...]:
        """Return entity-kind source rows, preserving duplicate codes."""
        return self._data.kind_rows

    def get_domain_choices(self, kind: KindCode) -> tuple[CatalogChild, ...]:
        """Return domain source rows applicable to one kind, preserving duplicates."""
        return tuple(row for parent, row in self._data.domain_rows if parent == kind)

    def _ambiguous_country_names(self) -> dict[CountryCode, tuple[str, ...]]:
        descriptions: dict[CountryCode, list[str]] = {}
        for row in self._data.country_rows:
            code = cast(CountryCode, row.value)
            descriptions.setdefault(code, []).append(row.description)
        return {code: tuple(values) for code, values in descriptions.items() if len(values) > 1}

    def get_all_domains(self) -> dict[tuple[KindCode, DomainCode], str]:
        """Return each domain with its kind, preserving kind-specific code spaces."""
        grouped: dict[tuple[KindCode, DomainCode], list[str]] = {}
        for kind, row in self._data.domain_rows:
            grouped.setdefault((kind, cast(DomainCode, row.value)), []).append(row.description)
        duplicate = next(((key, tuple(values)) for key, values in grouped.items() if len(values) > 1), None)
        if duplicate is not None:
            _raise_ambiguous_enumeration_name("Domain", *duplicate)
        return dict(self._data.domains)

    def get_all_kinds(self) -> dict[KindCode, str]:
        duplicate = _duplicate_descriptions(self._data.kind_rows, lambda row: row.value)
        if duplicate is not None:
            _raise_ambiguous_enumeration_name("Entity kind", *duplicate)
        return dict(self._data.kinds)

    def get_all_domains_of(self, kind: KindCode) -> dict[DomainCode, str]:
        duplicate = _duplicate_descriptions(self.get_domain_choices(kind), lambda row: row.value)
        if duplicate is not None:
            _raise_ambiguous_enumeration_name("Domain", *duplicate)
        return {
            domain: text for (parent_kind, domain), text in self._data.domains.items() if parent_kind == kind
        }

    def _children(self, parents: tuple[EntityFieldCode, ...]) -> dict[EntityFieldCode, str]:
        if parents not in self._children_cache:
            self._children_cache[parents] = _children_for(self._data.children_by_prefix, parents)
        return dict(self._children_cache[parents])

    def get_choice_rows(self, parents: tuple[EntityFieldCode, ...]) -> tuple[CatalogChild, ...]:
        """Return hierarchy choice rows without collapsing duplicate source codes."""
        return _choice_rows_for(self._data.children_by_prefix, parents)

    def get_all_categories_of(self, entity: EntityType) -> dict[CategoryCode, str]:
        return cast(dict[CategoryCode, str], self._children(entity.as_tuple()[:3]))

    def get_all_subcategories_of(self, entity: EntityType) -> dict[SubcategoryCode, str]:
        return cast(dict[SubcategoryCode, str], self._children(entity.as_tuple()[:4]))

    def get_all_specifics_of(self, entity: EntityType) -> dict[SpecificCode, str]:
        return cast(dict[SpecificCode, str], self._children(entity.as_tuple()[:5]))

    def get_all_extras_of(self, entity: EntityType) -> dict[ExtraCode, str]:
        return cast(dict[ExtraCode, str], self._children(entity.as_tuple()[:6]))

    def get_country_name(self, country: CountryCode) -> str:
        ambiguous = self._ambiguous_country_names().get(country)
        if ambiguous is not None:
            raise SisoRef010ValueError(
                f"Country code {country} has multiple source descriptions",
                code="ambiguous_country_name",
                context={"country": int(country), "candidate_descriptions": ambiguous},
            )
        return self._data.countries.get(country) or f"Unknown country {country}"

    def get_kind_name(self, kind: KindCode) -> str:
        duplicate = _duplicate_descriptions(
            tuple(row for row in self._data.kind_rows if row.value == kind),
            lambda row: row.value,
        )
        if duplicate is not None:
            _raise_ambiguous_enumeration_name("Entity kind", *duplicate)
        return self._data.kinds.get(kind) or f"Unknown kind {kind}"

    def get_domain_name(self, entity: EntityType) -> str:
        return self.get_all_domains_of(entity.kind).get(entity.domain) or f"Unknown domain {entity.domain}"

    def get_category_name(self, entity: EntityType) -> str:
        return (
            _child_description_for(self._data.children_by_prefix, entity.as_tuple()[:3], entity.category)
            or f"Unknown category {entity.category}"
        )

    def get_subcategory_name(self, entity: EntityType) -> str:
        return (
            _child_description_for(self._data.children_by_prefix, entity.as_tuple()[:4], entity.subcategory)
            or f"Unknown subcategory {entity.subcategory}"
        )

    def get_specific_name(self, entity: EntityType) -> str:
        return (
            _child_description_for(self._data.children_by_prefix, entity.as_tuple()[:5], entity.specific)
            or f"Unknown specific {entity.specific}"
        )

    def get_extra_name(self, entity: EntityType) -> str:
        return (
            _child_description_for(self._data.children_by_prefix, entity.as_tuple()[:6], entity.extra)
            or f"Unknown extra {entity.extra}"
        )

    def get_description_of(self, entity: EntityType, fully_qualified: bool = False) -> str:
        if not fully_qualified:
            return _description_for(self._data, entity)
        key = entity.to_key(signed=False)
        if key not in self._qualified_cache:
            parts = (
                self.get_category_name(entity),
                self.get_subcategory_name(entity),
                self.get_specific_name(entity),
                self.get_extra_name(entity),
            )
            self._qualified_cache[key] = " / ".join(
                part for index, part in enumerate(parts) if index == 0 or part != parts[index - 1]
            )
        return self._qualified_cache[key]

    def search_descriptions(self, query: str) -> dict[str, tuple[str, ...]]:
        """Search all hierarchy levels, returning deepest labels and their duplicate candidates."""
        return _search_descriptions(self._data, query)

    def search_description(self, query: str) -> dict[str, str]:
        """Search descriptions, raising rather than selecting an ambiguous label."""
        matches = self.search_descriptions(query)
        ambiguous = next(((entity, labels) for entity, labels in matches.items() if len(labels) > 1), None)
        if ambiguous is not None:
            entity, labels = ambiguous
            raise SisoRef010ValueError(
                f"Entity code {entity} matches multiple source descriptions",
                code="ambiguous_entity_description",
                context={"entity": entity, "candidate_descriptions": labels},
            )
        return {entity: labels[0] for entity, labels in matches.items()}
