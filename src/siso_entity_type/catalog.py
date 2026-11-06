# Modified work (2026): Python adaptation of TNO-MST/siso-entity-type.
# Original copyright 2025 TNO; Apache-2.0. See LICENSE and NOTICE.
"""Data-driven SISO lookup and search; adapted from TNO's Apache-2.0 library."""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path
from types import MappingProxyType
from typing import TypeAlias, TypedDict, cast

from .model import ENTITY_KIND_DESCRIPTIONS, UINT64_MAX, SisoEnum


class SisoEnumsData(TypedDict):
    subcategories: dict[str, str]
    categories: dict[str, str]
    countries: dict[str, str]
    domains: dict[str, str]


SisoEnumsDataType = SisoEnumsData
BITMAP_0 = 0
BITMAP_KIND = 0xFF00000000000000
BITMAP_KIND_DOMAIN = 0xFFFF000000000000
BITMAP_KIND_DOMAIN_COUNTRY = 0xFFFFFFFF00000000
BITMAP_COUNTRY = 0x0000FFFF00000000
BITMAP_COUNTRY_CAT = 0xFFFFFFFFFF000000
BITMAP_COUNTRY_CAT_SUBCAT = 0xFFFFFFFFFFFF0000
BITMAP_COUNTRY_CAT_SUBCAT_SPECIFIC = 0xFFFFFFFFFFFFFF00
BITMAP_0_CAT = 0xFFFF0000FF000000
BITMAP_0_CAT_SUBCAT = 0xFFFF0000FFFF0000
BITMAP_0_CAT_SUBCAT_SPECIFIC = 0xFFFF0000FFFFFF00
BITMAP_0_CAT_SUBCAT_SPECIFIC_EXTRA = 0xFFFF0000FFFFFFFF
BITMAP_BYTE = 0xFF
BITMAP_SHORT = 0xFFFF
BYTE_SHIFT = MappingProxyType(
    {"KIND": 56, "DOMAIN": 48, "COUNTRY": 32, "CATEGORY": 24, "SUBCATEGORY": 16, "SPECIFIC": 8, "EXTRA": 0}
)

# A collection is indexed by all parent fields. Stored ordinal preserves the
# original map's last-write-wins order when country-specific and generic rows mix.
_Index: TypeAlias = dict[tuple[int, ...], list[tuple[int, int, str]]]


def validate_data(value: object) -> SisoEnumsData:
    """Validate the four upstream JSON maps without unsafe float key coercion."""
    if not isinstance(value, dict):
        raise ValueError("SISO data must be an object containing four maps")
    obj = cast(dict[object, object], value)
    result: dict[str, dict[str, str]] = {}
    for name in ("subcategories", "categories", "countries", "domains"):
        raw = obj.get(name)
        if not isinstance(raw, dict):
            raise ValueError(f"Missing or invalid {name} map")
        entries = cast(dict[object, object], raw)
        output: dict[str, str] = {}
        for key, text in entries.items():
            if not isinstance(key, str) or not isinstance(text, str):
                raise ValueError(f"{name} must map decimal string keys to descriptions")
            try:
                number = int(key)
            except ValueError as exc:
                raise ValueError(f"Invalid {name} key: {key!r}") from exc
            if str(number) != key or not -(1 << 63) <= number <= UINT64_MAX:
                raise ValueError(f"Invalid 64-bit decimal {name} key: {key!r}")
            output[key] = text
        result[name] = output
    return cast(SisoEnumsData, result)


class SisoEnums:
    """A catalog initialized explicitly or loaded with :meth:`bundled`.

    Initializing replaces data atomically and invalidates indexes/caches.
    Returned mappings are copies, so callers cannot mutate the catalog.
    """

    def __init__(self, enums_map: SisoEnumsData | None = None) -> None:
        self._countries: dict[int, str] = {}
        self._domains: dict[int, str] = {}
        self._categories: dict[int, str] = {}
        self._subcategories: dict[int, str] = {}
        self._kinds: dict[int, str] = {}
        self._indexes: dict[int, _Index] = {level: {} for level in range(3, 7)}
        self._collections: dict[tuple[int, ...], dict[int, str]] = {}
        self._qualified: dict[int, str] = {}
        if enums_map is not None:
            self.initialize(enums_map)

    @classmethod
    def bundled(cls) -> SisoEnums:
        """Load the exact JSON snapshot from pinned upstream (SISO v35, 2025)."""
        return cls(
            validate_data(json.loads(files("siso_entity_type").joinpath("data/siso-enums.json").read_text()))
        )

    @classmethod
    def from_json(cls, path: str | Path) -> SisoEnums:
        return cls(validate_data(json.loads(Path(path).read_text(encoding="utf-8"))))

    def initialize(self, enums_map: SisoEnumsData) -> None:
        data = validate_data(enums_map)
        maps = {
            name: {int(key) & UINT64_MAX: text for key, text in entries.items()}
            for name, entries in (
                ("countries", data["countries"]),
                ("domains", data["domains"]),
                ("categories", data["categories"]),
                ("subcategories", data["subcategories"]),
            )
        }
        self._countries = maps["countries"]
        self._domains = maps["domains"]
        self._categories = maps["categories"]
        self._subcategories = maps["subcategories"]
        self._kinds = {int(kind): text for kind, text in ENTITY_KIND_DESCRIPTIONS.items()}
        self._indexes = {level: {} for level in range(3, 7)}
        for level in range(3, 7):
            source = self._categories if level == 3 else self._subcategories
            for ordinal, (key, text) in enumerate(source.items()):
                fields = SisoEnum.from_key(key).as_tuple()
                if any(fields[level + 1 :]):
                    continue
                prefix = fields[:level]
                self._indexes[level].setdefault(prefix, []).append((ordinal, fields[level], text))
        self._collections.clear()
        self._qualified.clear()

    @property
    def country_count(self) -> int:
        return len(self._countries)

    @property
    def kind_count(self) -> int:
        return len(self._kinds)

    @property
    def domain_count(self) -> int:
        return len(self._domains)

    @property
    def category_count(self) -> int:
        return len(self._categories)

    @property
    def subcategory_count(self) -> int:
        return len(self._subcategories)

    def get_all_countries(self) -> dict[int, str]:
        return {key >> 32: text for key, text in self._countries.items()}

    def get_all_domains(self) -> dict[int, str]:
        """Return upstream's composite keys: ``(kind << 8) | domain``."""
        return {key >> 48: text for key, text in self._domains.items()}

    def get_all_kinds(self) -> dict[int, str]:
        return dict(self._kinds)

    def get_all_domains_of(self, kind: int) -> dict[int, str]:
        return {(key >> 48) & 255: text for key, text in self._domains.items() if (key >> 56) & 255 == kind}

    def _children(self, parents: tuple[int, ...]) -> dict[int, str]:
        if parents in self._collections:
            return dict(self._collections[parents])
        level = len(parents)
        index = self._indexes[level]
        rows = list(index.get(parents, ()))
        if parents[2] != 0:
            generic = (*parents[:2], 0, *parents[3:])
            rows.extend(index.get(generic, ()))
            rows.sort(key=lambda row: row[0])
        result = {value: text for _, value, text in rows}
        self._collections[parents] = result
        return dict(result)

    def get_all_categories_of(self, kind: int, domain: int, country: int) -> dict[int, str]:
        return self._children((kind, domain, country))

    def get_all_subcategories_of(self, kind: int, domain: int, country: int, category: int) -> dict[int, str]:
        return self._children((kind, domain, country, category))

    def get_all_specifics_of(
        self, kind: int, domain: int, country: int, category: int, subcategory: int
    ) -> dict[int, str]:
        return self._children((kind, domain, country, category, subcategory))

    def get_all_extras_of(
        self, kind: int, domain: int, country: int, category: int, subcategory: int, specific: int
    ) -> dict[int, str]:
        return self._children((kind, domain, country, category, subcategory, specific))

    def get_country_name(self, country_or_entity: SisoEnum | int) -> str:
        country = country_or_entity.country if isinstance(country_or_entity, SisoEnum) else country_or_entity
        return self._countries.get(country << 32) or f"Unknown country {country}"

    def get_kind_name(self, kind_or_entity: SisoEnum | int) -> str:
        kind = kind_or_entity.kind if isinstance(kind_or_entity, SisoEnum) else kind_or_entity
        return self._kinds.get(kind) or f"Unknown kind {kind}"

    def get_domain_name(self, entity: SisoEnum) -> str:
        return self.get_all_domains_of(entity.kind).get(entity.domain) or f"Unknown domain {entity.domain}"

    def get_category_name(self, entity: SisoEnum) -> str:
        return (
            self._children(entity.as_tuple()[:3]).get(entity.category)
            or f"Unknown category {entity.category}"
        )

    def get_subcategory_name(self, entity: SisoEnum) -> str:
        return (
            self._children(entity.as_tuple()[:4]).get(entity.subcategory)
            or f"Unknown subcategory {entity.subcategory}"
        )

    def get_specific_name(self, entity: SisoEnum) -> str:
        return (
            self._children(entity.as_tuple()[:5]).get(entity.specific)
            or f"Unknown specific {entity.specific}"
        )

    def get_extra_name(self, entity: SisoEnum) -> str:
        return self._children(entity.as_tuple()[:6]).get(entity.extra) or f"Unknown extra {entity.extra}"

    def get_description_of(self, entity: SisoEnum, fully_qualified: bool = False) -> str:
        key = entity.to_key(signed=False)
        if fully_qualified:
            if key not in self._qualified:
                parts = [
                    self.get_category_name(entity),
                    self.get_subcategory_name(entity),
                    self.get_specific_name(entity),
                    self.get_extra_name(entity),
                ]
                self._qualified[key] = " / ".join(
                    part for i, part in enumerate(parts) if i == 0 or part != parts[i - 1]
                )
            return self._qualified[key]
        for source, masked in (
            (self._subcategories, key),
            (self._subcategories, key & BITMAP_0_CAT_SUBCAT_SPECIFIC_EXTRA),
            (self._subcategories, key & BITMAP_COUNTRY_CAT_SUBCAT_SPECIFIC),
            (self._subcategories, key & BITMAP_0_CAT_SUBCAT_SPECIFIC),
            (self._subcategories, key & BITMAP_COUNTRY_CAT_SUBCAT),
            (self._subcategories, key & BITMAP_0_CAT_SUBCAT),
            (self._categories, key & BITMAP_COUNTRY_CAT),
            (self._categories, key & BITMAP_KIND_DOMAIN_COUNTRY),
            (self._categories, key & BITMAP_0_CAT),
            (self._categories, key & BITMAP_KIND_DOMAIN),
        ):
            if masked in source:
                return source[masked]
        return "-"

    def search_description(self, query: str) -> dict[str, str]:
        """Case-insensitive substring search of subcategory/specific/extra rows only."""
        lower = query.lower()
        return {
            str(SisoEnum.from_key(key)): text
            for key, text in self._subcategories.items()
            if lower in text.lower()
        }

    countryCount = country_count
    kindCount = kind_count
    domainCount = domain_count
    categoryCount = category_count
    subcategoryCount = subcategory_count
    getAllCountries = get_all_countries
    getAllDomains = get_all_domains
    getAllKinds = get_all_kinds
    getAllDomainsOf = get_all_domains_of
    getAllCategoriesOf = get_all_categories_of
    getAllSubcategoriesOf = get_all_subcategories_of
    getAllSpecificsOf = get_all_specifics_of
    getAllExtrasOf = get_all_extras_of
    getCountryName = get_country_name
    getKindName = get_kind_name
    getDomainName = get_domain_name
    getCategoryName = get_category_name
    getSubcategoryName = get_subcategory_name
    getSpecificName = get_specific_name
    getExtraName = get_extra_name
    getDescriptionOf = get_description_of
    searchDescription = search_description
