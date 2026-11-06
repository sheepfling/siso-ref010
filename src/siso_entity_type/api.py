"""Public application API used by both Python consumers and the command line.

The lower-level SisoEnum, SisoEnums and parser APIs remain supported. This module
provides discoverable operations and immutable typed results with JSON-safe views.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TypedDict, cast

from ._version import DATA_DATE, DATA_VERSION, UPSTREAM_COMMIT, UPSTREAM_VERSION, __version__
from .catalog import SisoEnums
from .model import SisoEnum


class EntityFieldsJSON(TypedDict):
    kind: int
    domain: int
    country: int
    category: int
    subcategory: int
    specific: int
    extra: int


class EntityEncodingJSON(TypedDict):
    entity: str
    fields: EntityFieldsJSON
    key: str
    unsigned_key: str
    wire_hex: str


@dataclass(frozen=True, slots=True)
class EntityEncoding:
    """An entity's exact wire/key representation. JSON keys are decimal strings."""

    entity: SisoEnum

    @property
    def key(self) -> int:
        return self.entity.to_key()

    @property
    def unsigned_key(self) -> int:
        return self.entity.to_key(signed=False)

    @property
    def wire_bytes(self) -> bytes:
        return self.entity.to_bytes()

    def to_dict(self) -> EntityEncodingJSON:
        entity = self.entity
        return EntityEncodingJSON(
            entity=str(entity),
            fields=EntityFieldsJSON(
                kind=entity.kind,
                domain=entity.domain,
                country=entity.country,
                category=entity.category,
                subcategory=entity.subcategory,
                specific=entity.specific,
                extra=entity.extra,
            ),
            key=str(self.key),
            unsigned_key=str(self.unsigned_key),
            wire_hex=self.wire_bytes.hex(),
        )


def encode_entity(entity: SisoEnum | str) -> EntityEncoding:
    """Parse/validate an entity and expose its encoding without loading a catalog."""
    if isinstance(entity, str):
        return EntityEncoding(SisoEnum.from_string(entity))
    if not isinstance(cast(object, entity), SisoEnum):
        raise TypeError("entity must be a SisoEnum or a seven-field string")
    return EntityEncoding(entity)


def decode_key(key: int | str) -> EntityEncoding:
    """Decode a signed/unsigned integer or decimal/0x string; never pass a float."""
    if isinstance(key, str):
        value = key.strip()
        base = 16 if value.lower().lstrip("-+").startswith("0x") else 10
        key = int(value, base)
    return EntityEncoding(SisoEnum.from_key(key))


class EntityDescriptionJSON(EntityEncodingJSON):
    description: str
    qualified_description: str
    country_name: str
    kind_name: str
    domain_name: str


@dataclass(frozen=True, slots=True)
class EntityDescription:
    entity: SisoEnum
    description: str
    qualified_description: str
    country_name: str
    kind_name: str
    domain_name: str

    def to_dict(self) -> EntityDescriptionJSON:
        encoding = encode_entity(self.entity).to_dict()
        return EntityDescriptionJSON(
            **encoding,
            description=self.description,
            qualified_description=self.qualified_description,
            country_name=self.country_name,
            kind_name=self.kind_name,
            domain_name=self.domain_name,
        )


class SearchHitJSON(TypedDict):
    entity: str
    description: str


@dataclass(frozen=True, slots=True)
class SearchHit:
    entity: SisoEnum
    description: str

    def to_dict(self) -> SearchHitJSON:
        return SearchHitJSON(entity=str(self.entity), description=self.description)


class SearchResultsJSON(TypedDict):
    query: str
    total: int
    returned: int
    limit: int | None
    truncated: bool
    hits: list[SearchHitJSON]


@dataclass(frozen=True, slots=True)
class SearchResults:
    query: str
    total: int
    hits: tuple[SearchHit, ...]
    limit: int | None

    @property
    def truncated(self) -> bool:
        return len(self.hits) < self.total

    def to_dict(self) -> SearchResultsJSON:
        return SearchResultsJSON(
            query=self.query,
            total=self.total,
            returned=len(self.hits),
            limit=self.limit,
            truncated=self.truncated,
            hits=[hit.to_dict() for hit in self.hits],
        )


class Collection(StrEnum):
    COUNTRIES = "countries"
    KINDS = "kinds"
    DOMAINS = "domains"
    CATEGORIES = "categories"
    SUBCATEGORIES = "subcategories"
    SPECIFICS = "specifics"
    EXTRAS = "extras"


class ChoiceJSON(TypedDict):
    value: int
    description: str


@dataclass(frozen=True, slots=True)
class Choice:
    value: int
    description: str

    def to_dict(self) -> ChoiceJSON:
        return ChoiceJSON(value=self.value, description=self.description)


class ChoicesJSON(TypedDict):
    collection: str
    parents: list[int]
    choices: list[ChoiceJSON]


@dataclass(frozen=True, slots=True)
class Choices:
    collection: Collection
    parents: tuple[int, ...]
    items: tuple[Choice, ...]

    def to_dict(self) -> ChoicesJSON:
        return ChoicesJSON(
            collection=self.collection.value,
            parents=list(self.parents),
            choices=[choice.to_dict() for choice in self.items],
        )


class CatalogInfoJSON(TypedDict):
    version: str
    upstream_version: str
    upstream_commit: str
    data_source: str
    data_version: str | None
    data_date: str | None
    attribution: str
    counts: dict[str, int]


class EntityTypeAPI:
    """High-level typed API. Construct with no argument for the bundled snapshot.

    ``EntityTypeAPI(catalog)`` accepts an existing SisoEnums instance. Its data
    provenance is reported as supplied, never assumed to be the bundled version.
    ``from_json`` loads a custom JSON snapshot once. No method prints or exits.
    """

    def __init__(self, catalog: SisoEnums | None = None) -> None:
        self._catalog = catalog if catalog is not None else SisoEnums.bundled()
        self._bundled_data = catalog is None
        self._source = "bundled" if catalog is None else "supplied"

    @classmethod
    def from_json(cls, path: str | Path) -> EntityTypeAPI:
        result = cls(SisoEnums.from_json(path))
        result._source = str(path)
        return result

    def describe(self, entity: SisoEnum | str) -> EntityDescription:
        item = encode_entity(entity).entity
        return EntityDescription(
            entity=item,
            description=self._catalog.get_description_of(item),
            qualified_description=self._catalog.get_description_of(item, True),
            country_name=self._catalog.get_country_name(item),
            kind_name=self._catalog.get_kind_name(item),
            domain_name=self._catalog.get_domain_name(item),
        )

    def search(self, query: str, *, limit: int | None = None) -> SearchResults:
        """Search leaf descriptions. None means all, 0 means return no hits."""
        if limit is not None and (
            isinstance(limit, bool) or not isinstance(cast(object, limit), int) or limit < 0
        ):
            raise ValueError("limit must be a nonnegative integer or None")
        if not isinstance(cast(object, query), str):
            raise TypeError("query must be a string")
        matches = self._catalog.search_description(query)
        selected = list(matches.items())[:limit] if limit is not None else list(matches.items())
        hits = tuple(SearchHit(SisoEnum.from_string(entity), description) for entity, description in selected)
        return SearchResults(query, len(matches), hits, limit)

    def choices(self, collection: Collection | str, *parents: int) -> Choices:
        """List next-level choices. Parent order is kind/domain/country/category/subcategory/specific."""
        kind = Collection(collection)
        lengths = {
            Collection.COUNTRIES: 0,
            Collection.KINDS: 0,
            Collection.DOMAINS: 1,
            Collection.CATEGORIES: 3,
            Collection.SUBCATEGORIES: 4,
            Collection.SPECIFICS: 5,
            Collection.EXTRAS: 6,
        }
        if len(parents) != lengths[kind]:
            raise ValueError(f"{kind.value} requires {lengths[kind]} parent numbers")
        # Validate parents as wire fields without conflating unknown numeric codes with invalid values.
        SisoEnum(*parents, *((0,) * (7 - len(parents))))
        if kind == Collection.COUNTRIES:
            values = self._catalog.get_all_countries()
        elif kind == Collection.KINDS:
            values = self._catalog.get_all_kinds()
        elif kind == Collection.DOMAINS:
            values = self._catalog.get_all_domains_of(parents[0])
        elif kind == Collection.CATEGORIES:
            values = self._catalog.get_all_categories_of(*parents)
        elif kind == Collection.SUBCATEGORIES:
            values = self._catalog.get_all_subcategories_of(*parents)
        elif kind == Collection.SPECIFICS:
            values = self._catalog.get_all_specifics_of(*parents)
        else:
            values = self._catalog.get_all_extras_of(*parents)
        return Choices(kind, parents, tuple(Choice(value, text) for value, text in values.items()))

    def info(self) -> CatalogInfoJSON:
        bundled = self._bundled_data
        catalog = self._catalog
        return CatalogInfoJSON(
            version=__version__,
            upstream_version=UPSTREAM_VERSION,
            upstream_commit=UPSTREAM_COMMIT,
            data_source=self._source,
            data_version=DATA_VERSION if bundled else None,
            data_date=DATA_DATE if bundled else None,
            attribution="Reprinted with permission from SISO Inc.",
            counts={
                "countries": catalog.country_count,
                "kinds": catalog.kind_count,
                "domains": catalog.domain_count,
                "categories": catalog.category_count,
                "subcategories": catalog.subcategory_count,
            },
        )


__all__ = [
    "EntityTypeAPI",
    "EntityEncoding",
    "EntityDescription",
    "SearchHit",
    "SearchResults",
    "Collection",
    "Choice",
    "Choices",
    "encode_entity",
    "decode_key",
    "EntityFieldsJSON",
    "EntityEncodingJSON",
    "EntityDescriptionJSON",
    "SearchHitJSON",
    "SearchResultsJSON",
    "ChoiceJSON",
    "ChoicesJSON",
    "CatalogInfoJSON",
]
