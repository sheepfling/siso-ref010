"""Public application API used by both Python consumers and the command line.

This module provides discoverable operations and immutable typed results with
JSON-safe views. Use `EntityTypeCatalog` and `EntityTypeXmlParser` for lower-level access.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from enum import StrEnum
from types import MappingProxyType
from typing import Final, cast

from pydantic import BaseModel, ConfigDict, Field, computed_field

from ._paths import PathInput, normalize_path
from ._version import __version__
from .catalog import BUNDLED_STANDARD_VERSION, BUNDLED_STANDARD_VERSIONS, EntityTypeCatalog
from .codes import EntityFieldCode
from .comparison import (
    ComparisonScope,
    EditionDiff,
    ValueHistory,
)
from .comparison import (
    compare_editions as _compare_editions,
)
from .comparison import (
    entity_history as _entity_history,
)
from .comparison import (
    enumeration_history as _enumeration_history,
)
from .errors import EntityTypeTypeError, EntityTypeValueError
from .inspection import (
    EditionInspector,
    EditionValue,
    EntityExplanation,
    EntityResolution,
    EnumerationTableInfo,
    EnumerationValueResolution,
)
from .model import EntityType, EntityTypePrefix
from .query_backend import (
    EntityQueryBackend,
    EntityQueryPage,
    EntityQueryRequest,
    MappingEntityQueryBackend,
)
from .sources import BUNDLED_STANDARD_SOURCE, BundledStandardSource, StandardSource


class ResultModel(BaseModel):
    """Immutable API result with Pydantic-backed JSON serialization."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class EntityEncoding(ResultModel):
    """An entity's exact wire/key representation. JSON keys are decimal strings."""

    entity: EntityType

    @property
    def key(self) -> int:
        return self.entity.to_key()

    @property
    def unsigned_key(self) -> int:
        return self.entity.to_key(signed=False)

    @property
    def wire_bytes(self) -> bytes:
        return self.entity.to_bytes()

    @computed_field(alias="key")
    @property
    def key_decimal(self) -> str:
        return str(self.key)

    @computed_field(alias="unsigned_key")
    @property
    def unsigned_key_decimal(self) -> str:
        return str(self.unsigned_key)

    @computed_field(alias="wire_hex")
    @property
    def wire_hex_value(self) -> str:
        return self.wire_bytes.hex()


def encode_entity(entity: EntityType | str) -> EntityEncoding:
    """Parse/validate an entity and expose its encoding without loading a catalog."""
    if isinstance(entity, str):
        return EntityEncoding(entity=EntityType.from_string(entity))
    if not isinstance(cast(object, entity), EntityType):
        raise EntityTypeTypeError(
            "entity must be a EntityType or a seven-field string",
            code="invalid_entity_type",
            context={"received_type": type(entity).__name__, "expected": "EntityType or str"},
        )
    return EntityEncoding(entity=entity)


def decode_key(key: int | str) -> EntityEncoding:
    """Decode a signed/unsigned integer or decimal/0x string; never pass a float."""
    if isinstance(key, str):
        value = key.strip()
        base = 16 if value.lower().lstrip("-+").startswith("0x") else 10
        key = int(value, base)
    return EntityEncoding(entity=EntityType.from_key(key))


class EntityDescription(EntityEncoding):
    description: str
    qualified_description: str
    country_name: str
    kind_name: str
    domain_name: str


class SearchHit(ResultModel):
    entity: EntityType
    description: str


class SearchResults(ResultModel):
    query: str
    total: int
    hits: tuple[SearchHit, ...]
    limit: int | None

    @computed_field
    @property
    def returned(self) -> int:
        return len(self.hits)

    @computed_field
    @property
    def truncated(self) -> bool:
        return len(self.hits) < self.total


class EntityQueryResults(ResultModel):
    """A page of source entity records matching structured field filters."""

    title: str
    date: str
    entity_kind: int | None
    domain: int | None
    country: int | None
    category: int | None
    subcategory: int | None
    specific: int | None
    extra: int | None
    text: str | None
    total: int
    values: tuple[EditionValue, ...]
    limit: int | None
    offset: int

    @computed_field
    @property
    def returned(self) -> int:
        return len(self.values)

    @computed_field
    @property
    def truncated(self) -> bool:
        return self.offset + len(self.values) < self.total


class EntityQueryWarmup(ResultModel):
    """Summary of a structured-query backend warmup for one edition."""

    title: str
    date: str
    backend: str
    indexed_records: int | None


class EnumerationNameStatus(StrEnum):
    """Outcome when resolving an enumeration by its human-readable table name."""

    TABLE_NOT_FOUND = "table_not_found"
    AMBIGUOUS_TABLE = "ambiguous_table"
    EXACT = "exact"
    RANGE = "range"
    UNKNOWN = "unknown"
    AMBIGUOUS_VALUE = "ambiguous_value"


class EnumerationNameResolution(ResultModel):
    """Range-aware value results for every table matching an exact table name."""

    name: str
    value: int
    status: EnumerationNameStatus
    matches: tuple[EnumerationValueResolution, ...]

    @property
    def match(self) -> EditionValue | None:
        """Return the one unambiguous exact/range row, or ``None`` otherwise."""
        if self.status not in (EnumerationNameStatus.EXACT, EnumerationNameStatus.RANGE):
            return None
        if len(self.matches) != 1 or len(self.matches[0].matches) != 1:
            return None
        return self.matches[0].matches[0]


class Collection(StrEnum):
    COUNTRIES = "countries"
    KINDS = "kinds"
    DOMAINS = "domains"
    CATEGORIES = "categories"
    SUBCATEGORIES = "subcategories"
    SPECIFICS = "specifics"
    EXTRAS = "extras"

    @property
    def parent_count(self) -> int:
        """Number of entity fields required to select this collection."""
        return _PARENT_COUNTS[self]  # noqa


_PARENT_COUNTS: Final = MappingProxyType(
    {
        Collection.COUNTRIES: 0,
        Collection.KINDS: 0,
        Collection.DOMAINS: 1,
        Collection.CATEGORIES: 3,
        Collection.SUBCATEGORIES: 4,
        Collection.SPECIFICS: 5,
        Collection.EXTRAS: 6,
    }
)


class Choice(ResultModel):
    value: EntityFieldCode
    description: str


class CatalogCounts(ResultModel):
    countries: int
    kinds: int
    domains: int
    categories: int
    subcategories: int


class Choices(ResultModel):
    collection: Collection
    parents: tuple[EntityFieldCode, ...]
    items: tuple[Choice, ...] = Field(serialization_alias="choices")


class CatalogInfo(ResultModel):
    version: str
    data_source: str
    data_version: str | None
    data_date: str | None
    attribution: str
    counts: CatalogCounts


class BundledStandards(ResultModel):
    """Discoverable list of bundled standards and the default selection."""

    default_version: int
    versions: tuple[int, ...]


def _validated_prefix(value: object) -> EntityTypePrefix | None:
    if value is None or isinstance(value, EntityTypePrefix):
        return value
    raise EntityTypeTypeError(
        "prefix must be an EntityTypePrefix or None",
        code="invalid_entity_prefix_type",
        context={"received_type": type(value).__name__, "expected": "EntityTypePrefix or None"},
    )


class EntityTypeAPI:
    """High-level typed API. Construct with no argument for the bundled snapshot.

    ``EntityTypeAPI(catalog)`` accepts an existing EntityTypeCatalog instance. Its data
    provenance is reported as supplied, never assumed to be the bundled version.
    ``from_xml`` loads another SISO-REF-010 XML source once. Pass ``query_backend``
    to replace structured query execution. No method prints or exits.
    """

    def __init__(
        self,
        catalog: EntityTypeCatalog | None = None,
        *,
        query_backend: EntityQueryBackend | None = None,
    ) -> None:
        self._catalog = catalog if catalog is not None else EntityTypeCatalog.bundled()
        self._source = "bundled" if catalog is None else "supplied"
        self._verified_standard = self._catalog.standard if catalog is None else None
        self._edition_number = BUNDLED_STANDARD_VERSION if catalog is None else None
        self._inspector: EditionInspector | None = None
        self._query_backend = query_backend if query_backend is not None else MappingEntityQueryBackend()

    @classmethod
    def bundled(
        cls,
        version: int = BUNDLED_STANDARD_VERSION,
        *,
        query_backend: EntityQueryBackend | None = None,
    ) -> EntityTypeAPI:
        """Load one of the bundled SISO-REF-010 editions by its release number."""
        result = cls(EntityTypeCatalog.bundled(version), query_backend=query_backend)
        result._source = "bundled"
        result._verified_standard = result._catalog.standard
        result._edition_number = version
        return result

    @classmethod
    def bundled_versions(cls) -> BundledStandards:
        """Return the bundled editions and default release without loading XML."""
        return BundledStandards(
            default_version=BUNDLED_STANDARD_VERSION,
            versions=BUNDLED_STANDARD_VERSIONS,
        )

    @classmethod
    def from_xml(
        cls,
        path: PathInput,
        *,
        query_backend: EntityQueryBackend | None = None,
    ) -> EntityTypeAPI:
        source = normalize_path(path)
        result = cls(EntityTypeCatalog.from_xml(source), query_backend=query_backend)
        result._source = str(source)
        return result

    @classmethod
    def from_source(
        cls,
        source: StandardSource,
        version: int,
        *,
        query_backend: EntityQueryBackend | None = None,
    ) -> EntityTypeAPI:
        """Retrieve one version from a pluggable standard source."""
        result = cls(EntityTypeCatalog.from_source(source, version), query_backend=query_backend)
        is_bundled = type(source) is BundledStandardSource
        result._source = "bundled" if is_bundled else "supplied"
        result._verified_standard = result._catalog.standard if is_bundled else None
        result._edition_number = version if is_bundled else None
        return result

    @classmethod
    def iter_editions(
        cls,
        source: StandardSource | None = None,
        versions: Iterable[int] | None = None,
    ) -> Iterator[tuple[int, EntityTypeAPI]]:
        """Yield APIs by version for the same query across multiple editions."""
        selected_source = source if source is not None else BUNDLED_STANDARD_SOURCE
        selected_versions = selected_source.versions if versions is None else tuple(versions)
        for version in selected_versions:
            yield version, cls.from_source(selected_source, version)

    @classmethod
    def entity_history(
        cls,
        entity: EntityType | str,
        *,
        source: StandardSource | None = None,
        versions: Iterable[int] | None = None,
    ) -> ValueHistory:
        """Inspect one entity code's effective description across editions."""
        selected_source = source if source is not None else BUNDLED_STANDARD_SOURCE
        return _entity_history(entity, source=selected_source, versions=versions)

    @classmethod
    def enumeration_history(
        cls,
        uid: int,
        value: int | None = None,
        *,
        source: StandardSource | None = None,
        versions: Iterable[int] | None = None,
    ) -> ValueHistory:
        """Inspect one enumeration table or value across editions."""
        selected_source = source if source is not None else BUNDLED_STANDARD_SOURCE
        return _enumeration_history(uid, value, source=selected_source, versions=versions)

    @classmethod
    def compare_editions(
        cls,
        from_version: int,
        to_version: int,
        *,
        source: StandardSource | None = None,
        scope: ComparisonScope = "all",
        entity_prefix: tuple[int, ...] | None = None,
        enumeration_uid: int | None = None,
        limit: int | None = 500,
    ) -> EditionDiff:
        """Return semantic changes between two editions with optional scope filters."""
        selected_source = source if source is not None else BUNDLED_STANDARD_SOURCE
        return _compare_editions(
            from_version,
            to_version,
            source=selected_source,
            scope=scope,
            entity_prefix=entity_prefix,
            enumeration_uid=enumeration_uid,
            limit=limit,
        )

    @property
    def inspector(self) -> EditionInspector:
        """Return a read-only inspector for the exact parsed edition in this API."""
        standard = self._catalog.standard
        if standard is None:
            raise EntityTypeValueError(
                "No parsed SISO-REF-010 source is available for inspection",
                code="missing_standard_source",
                context={"data_source": self._source},
            )
        if self._inspector is None or self._inspector.standard is not standard:
            self._inspector = EditionInspector(
                standard,
                provenance_status="bundled_checksum_verified"
                if standard is self._verified_standard
                else "unverified",
                edition_number=self._edition_number,
            )
        return self._inspector

    def describe(self, entity: EntityType | str) -> EntityDescription:
        item = encode_entity(entity).entity
        return EntityDescription(
            entity=item,
            description=self._catalog.get_description_of(item),
            qualified_description=self._catalog.get_description_of(item, True),
            country_name=self._catalog.get_country_name(item.country),
            kind_name=self._catalog.get_kind_name(item.kind),
            domain_name=self._catalog.get_domain_name(item),
        )

    def explain_entity(self, entity: EntityType | EntityTypePrefix | str) -> EntityExplanation:
        """Explain a full code or prefix and explicitly report unresolved components."""
        resolution = self.resolve_entity(entity)
        labels = tuple(row.description for row in resolution.matched_path if row.description)
        description = labels[-1] if labels else ""
        return EntityExplanation(
            entity=resolution.code,
            description=description,
            qualified_description=" / ".join(labels),
            path=resolution.matched_path,
            resolution=resolution,
        )

    def resolve_entity(self, entity: EntityType | EntityTypePrefix | str) -> EntityResolution:
        """Resolve a code or contiguous prefix with explicit match semantics.

        Dotted strings may contain one through seven unsigned decimal fields.
        Strings with fewer than seven fields are interpreted as prefixes.
        """
        if isinstance(entity, str):
            parts = entity.split(".")
            if len(parts) < 7 and all(re.fullmatch(r"[0-9]+", part.strip()) for part in parts):
                fields = tuple(
                    EntityTypePrefix.from_values(tuple(int(part.strip()) for part in parts)).values
                )
            else:
                fields = EntityType.from_string(entity).as_tuple()
        elif isinstance(entity, EntityType):
            fields = entity.as_tuple()
        elif isinstance(cast(object, entity), EntityTypePrefix):
            fields = tuple(entity.values)
        else:
            raise EntityTypeTypeError(
                "entity must be an EntityType, EntityTypePrefix, or dotted code/prefix string",
                code="invalid_entity_resolution_input",
                context={"received_type": type(entity).__name__},
            )
        return self.inspector.resolve_entity(fields)

    def resolve_enumeration_value(self, uid: int, value: int) -> EnumerationValueResolution:
        """Resolve a table value to its exact source row or covering range."""
        return self.inspector.resolve_enumeration_value(uid, value)

    def find_enumeration_tables(self, name: str) -> tuple[EnumerationTableInfo, ...]:
        """Find tables by exact, case-insensitive human-readable name."""
        if not isinstance(cast(object, name), str):
            raise EntityTypeTypeError(
                "enumeration name must be a string",
                code="invalid_enumeration_name_type",
                context={"received_type": type(name).__name__},
            )
        normalized = name.strip().casefold()
        if not normalized:
            raise EntityTypeValueError(
                "enumeration name must not be empty",
                code="empty_enumeration_name",
                context={"name": name},
            )
        return tuple(
            table
            for table in self.inspector.enumeration_tables()
            if table.name.strip().casefold() == normalized
        )

    def resolve_enumeration(self, name: str, value: int) -> EnumerationNameResolution:
        """Resolve a value by exact table name without requiring its UID first.

        Duplicate table names are preserved in ``matches`` and reported as
        ``ambiguous_table`` instead of selecting an arbitrary UID.
        """
        if type(value) is not int:
            raise EntityTypeTypeError(
                "enumeration value must be an integer, not a boolean",
                code="invalid_enumeration_value_type",
                context={"value": value, "expected": "integer"},
            )
        if value < 0:
            raise EntityTypeValueError(
                "enumeration value must be nonnegative",
                code="negative_enumeration_value",
                context={"value": value, "minimum": 0},
            )
        tables = self.find_enumeration_tables(name)
        matches = tuple(self.inspector.resolve_enumeration_value(table.uid, value) for table in tables)
        if not tables:
            status = EnumerationNameStatus.TABLE_NOT_FOUND
        elif len(tables) > 1 or len(matches[0].tables) > 1:
            status = EnumerationNameStatus.AMBIGUOUS_TABLE
        else:
            status = {
                "exact": EnumerationNameStatus.EXACT,
                "range": EnumerationNameStatus.RANGE,
                "unknown": EnumerationNameStatus.UNKNOWN,
                "ambiguous": EnumerationNameStatus.AMBIGUOUS_VALUE,
            }[matches[0].status.value]
        return EnumerationNameResolution(name=name, value=value, status=status, matches=matches)

    def warmup(self) -> EntityQueryWarmup:
        """Build the selected edition's structured-query indexes before a request."""
        inspector = self.inspector
        return EntityQueryWarmup(
            title=inspector.title,
            date=inspector.date,
            backend=type(self._query_backend).__name__,
            indexed_records=self._query_backend.warmup(inspector),
        )

    def search(self, query: str, *, limit: int | None = None) -> SearchResults:
        """Search descriptions; None returns all, while zero returns no hits."""
        if limit is not None and (
            isinstance(limit, bool) or not isinstance(cast(object, limit), int) or limit < 0
        ):
            raise EntityTypeValueError(
                "limit must be a nonnegative integer or None",
                code="invalid_search_limit",
                context={"value": limit, "minimum": 0},
            )
        if not isinstance(cast(object, query), str):
            raise EntityTypeTypeError(
                "query must be a string",
                code="invalid_query_type",
                context={"received_type": type(query).__name__, "expected": "str"},
            )
        matches = self._catalog.search_description(query)
        selected = list(matches.items())[:limit] if limit is not None else list(matches.items())
        hits = tuple(
            SearchHit(entity=EntityType.from_string(entity), description=description)
            for entity, description in selected
        )
        return SearchResults(query=query, total=len(matches), hits=hits, limit=limit)

    def query_entities(
        self,
        *,
        entity_kind: int | None = None,
        domain: int | None = None,
        country: int | None = None,
        category: int | None = None,
        subcategory: int | None = None,
        specific: int | None = None,
        extra: int | None = None,
        text: str | None = None,
        limit: int | None = 100,
        offset: int = 0,
    ) -> EntityQueryResults:
        """Filter source entity records by any combination of code fields and text.

        Field filters are independent, so callers can filter on country without
        also specifying kind or domain. Numeric range rows match when the
        requested field value falls within the source range. Country-zero rows
        match a nonzero country filter because the standard uses them as generic
        country entries.
        """
        filters = (entity_kind, domain, country, category, subcategory, specific, extra)
        maxima = (255, 255, 65535, 255, 255, 255, 255)
        names = ("entity_kind", "domain", "country", "category", "subcategory", "specific", "extra")
        for name, value, maximum in zip(names, filters, maxima, strict=True):
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(cast(object, value), int)
                or not 0 <= value <= maximum
            ):
                raise EntityTypeValueError(
                    f"{name} must be an integer from 0 through {maximum}",
                    code="invalid_entity_query_field",
                    context={"field": name, "value": value, "minimum": 0, "maximum": maximum},
                )
        if text is not None and not isinstance(cast(object, text), str):
            raise EntityTypeTypeError(
                "text must be a string or None",
                code="invalid_entity_query_text",
                context={"received_type": type(text).__name__, "expected": "str or None"},
            )
        invalid_limit = isinstance(limit, bool) or (
            limit is not None and (not isinstance(cast(object, limit), int) or limit < 0)
        )
        if invalid_limit:
            raise EntityTypeValueError(
                "limit must be a nonnegative integer or None",
                code="invalid_entity_query_limit",
                context={"value": limit, "minimum": 0},
            )
        if isinstance(offset, bool) or not isinstance(cast(object, offset), int) or offset < 0:
            raise EntityTypeValueError(
                "offset must be a nonnegative integer",
                code="invalid_entity_query_offset",
                context={"value": offset, "minimum": 0},
            )

        inspector = self.inspector
        standard = inspector.standard
        page = self._query_backend.query(
            inspector,
            EntityQueryRequest(
                entity_kind=entity_kind,
                domain=domain,
                country=country,
                category=category,
                subcategory=subcategory,
                specific=specific,
                extra=extra,
                text=text,
                limit=limit,
                offset=offset,
            ),
        )
        return EntityQueryResults(
            title=standard.title,
            date=standard.date.isoformat() if standard.date is not None else "",
            entity_kind=entity_kind,
            domain=domain,
            country=country,
            category=category,
            subcategory=subcategory,
            specific=specific,
            extra=extra,
            text=text,
            total=page.total,
            values=page.values,
            limit=limit,
            offset=offset,
        )

    def choices(self, collection: Collection | str, prefix: EntityTypePrefix | None = None) -> Choices:
        """List choices beneath a validated entity-field prefix."""
        kind = Collection(collection)
        prefix = _validated_prefix(prefix)
        parents = prefix.values if prefix is not None else ()
        if len(parents) != kind.parent_count:
            raise EntityTypeValueError(
                f"{kind.value} requires {kind.parent_count} parent numbers",
                code="invalid_parent_count",
                context={
                    "collection": kind.value,
                    "received": len(parents),
                    "expected": kind.parent_count,
                },
            )
        entity = prefix.to_entity() if prefix is not None else EntityType(0, 0, 0, 0, 0, 0, 0)
        match kind:
            case Collection.COUNTRIES:
                values = self._catalog.get_all_countries()
            case Collection.KINDS:
                values = self._catalog.get_all_kinds()
            case Collection.DOMAINS:
                values = self._catalog.get_all_domains_of(entity.kind)
            case Collection.CATEGORIES:
                values = self._catalog.get_all_categories_of(entity)
            case Collection.SUBCATEGORIES:
                values = self._catalog.get_all_subcategories_of(entity)
            case Collection.SPECIFICS:
                values = self._catalog.get_all_specifics_of(entity)
            case Collection.EXTRAS:
                values = self._catalog.get_all_extras_of(entity)
        return Choices(
            collection=kind,
            parents=parents,
            items=tuple(Choice(value=value, description=text) for value, text in values.items()),
        )

    def info(self) -> CatalogInfo:
        catalog = self._catalog
        standard = catalog.standard
        return CatalogInfo(
            version=__version__,
            data_source=self._source,
            data_version=(standard.title or None) if standard is not None else None,
            data_date=standard.date.isoformat() if standard is not None and standard.date else None,
            attribution="Reprinted with permission from SISO Inc.",
            counts=CatalogCounts(
                countries=catalog.country_count,
                kinds=catalog.kind_count,
                domains=catalog.domain_count,
                categories=catalog.category_count,
                subcategories=catalog.subcategory_count,
            ),
        )


__all__ = [
    "EntityTypeAPI",
    "EntityEncoding",
    "EntityDescription",
    "SearchHit",
    "SearchResults",
    "EntityQueryResults",
    "EntityQueryWarmup",
    "EntityQueryBackend",
    "EntityQueryPage",
    "EntityQueryRequest",
    "MappingEntityQueryBackend",
    "Collection",
    "Choice",
    "Choices",
    "encode_entity",
    "decode_key",
    "CatalogInfo",
    "CatalogCounts",
    "BundledStandards",
    "EntityExplanation",
]
