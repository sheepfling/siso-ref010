# Modified work (2026): Python adaptation of TNO-MST/siso-entity-type.
# Original copyright 2025 TNO; Apache-2.0. See LICENSE and NOTICE.
"""Entity types and exact 64-bit keys, ported from TNO's Apache-2.0 source.

The Python model validates wire fields rather than silently coercing malformed input.
``create_key`` remains the low-level, masking-compatible integer helper.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from enum import IntEnum
from types import MappingProxyType
from typing import Final


class EntityKind(IntEnum):
    OTHER = 0
    PLATFORM = 1
    MUNITION = 2
    LIFE_FORM = 3
    ENVIRONMENTAL = 4
    CULTURAL_FEATURE = 5
    SUPPLY = 6
    RADIO = 7
    EXPENDABLE = 8
    SENSOR_EMITTER = 9

    Other = OTHER
    Platform = PLATFORM
    Munition = MUNITION
    LifeForm = LIFE_FORM
    Environmental = ENVIRONMENTAL
    CulturalFeature = CULTURAL_FEATURE
    Supply = SUPPLY
    Radio = RADIO
    Expendable = EXPENDABLE
    SensorEmitter = SENSOR_EMITTER


class EntityDomain(IntEnum):
    """Platform domains. Munition and supply domains use different code sets."""

    OTHER = 0
    LAND = 1
    AIR = 2
    SURFACE = 3
    SUBSURFACE = 4
    SPACE = 5

    Other = OTHER
    Land = LAND
    Air = AIR
    Surface = SURFACE
    Subsurface = SUBSURFACE
    Space = SPACE


ENTITY_KIND_DESCRIPTIONS: Final = MappingProxyType(
    dict(
        zip(
            EntityKind,
            (
                "Other",
                "Platform",
                "Munition",
                "Life form",
                "Environmental",
                "Cultural feature",
                "Supply",
                "Radio",
                "Expendable",
                "Sensor/Emitter",
            ),
            strict=True,
        )
    )
)
ENTITY_DOMAIN_DESCRIPTIONS: Final = MappingProxyType(
    dict(zip(EntityDomain, ("Other", "Land", "Air", "Surface", "Subsurface", "Space"), strict=True))
)
_KIND_JS_NAMES: Final = (
    "Other",
    "Platform",
    "Munition",
    "LifeForm",
    "Environmental",
    "CulturalFeature",
    "Supply",
    "Radio",
    "Expendable",
    "SensorEmitter",
)
_SHIFTS: Final = (56, 48, 32, 24, 16, 8, 0)
_LIMITS: Final = (255, 255, 65535, 255, 255, 255, 255)
_NAMES: Final = ("kind", "domain", "country", "category", "subcategory", "specific", "extra")
UINT64_MAX: Final = (1 << 64) - 1


def create_entity_kind_from_number(value: int | float) -> EntityKind | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, float):
        if not value.is_integer():
            return None
        value = int(value)
    try:
        return EntityKind(value)
    except (ValueError, TypeError):
        return None


def create_entity_domain_from_number(value: int | float) -> EntityDomain | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, float):
        if not value.is_integer():
            return None
        value = int(value)
    try:
        return EntityDomain(value)
    except (ValueError, TypeError):
        return None


def create_entity_kind_from_string(name: str) -> EntityKind | None:
    normalized = name.lower().replace("/", "").replace(" ", "")
    return next(
        (
            kind
            for kind, text in ENTITY_KIND_DESCRIPTIONS.items()
            if text.lower().replace("/", "").replace(" ", "") == normalized
        ),
        None,
    )


def create_entity_domain_from_string(name: str) -> EntityDomain | None:
    return next(
        (domain for domain, text in ENTITY_DOMAIN_DESCRIPTIONS.items() if text.lower() == name.lower()), None
    )


def get_entity_kind_description(kind: int) -> str | None:
    value = create_entity_kind_from_number(kind)
    return ENTITY_KIND_DESCRIPTIONS.get(value) if value is not None else None


def get_entity_domain_description(domain: int) -> str | None:
    value = create_entity_domain_from_number(domain)
    return ENTITY_DOMAIN_DESCRIPTIONS.get(value) if value is not None else None


def _is_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def create_key(
    kind: int,
    domain: int,
    country: int,
    category: int,
    subcategory: int,
    specific: int,
    extra: int,
    *,
    signed: bool = True,
) -> int:
    """Pack integers, masking each field as upstream does; signed by default.

    Use ``SisoEnum`` when field bounds must be validated. No floats, strings or
    booleans are implicitly coerced. Pass ``signed=False`` for an unsigned key.
    """
    key = 0
    for value, shift, limit in zip(
        (kind, domain, country, category, subcategory, specific, extra), _SHIFTS, _LIMITS, strict=True
    ):
        if not _is_integer(value):
            raise TypeError("Entity fields must be integers, not booleans")
        key |= (value & limit) << shift
    return key - (1 << 64) if signed and key >= (1 << 63) else key


@dataclass(frozen=True, slots=True)
class SisoEnum:
    kind: int
    domain: int
    country: int
    category: int
    subcategory: int
    specific: int
    extra: int

    def __post_init__(self) -> None:
        for name, value, limit in zip(_NAMES, self.as_tuple(), _LIMITS, strict=True):
            if not _is_integer(value):
                raise TypeError(f"{name} must be an integer, not a boolean")
            if not 0 <= value <= limit:
                raise ValueError(f"{name} must be in 0..{limit}, got {value}")

    def as_tuple(self) -> tuple[int, int, int, int, int, int, int]:
        return (
            self.kind,
            self.domain,
            self.country,
            self.category,
            self.subcategory,
            self.specific,
            self.extra,
        )

    def get_kind(self) -> EntityKind | None:
        return create_entity_kind_from_number(self.kind)

    def get_domain(self) -> EntityDomain | None:
        """Return the platform-domain enum, as upstream; use catalog names for other kinds."""
        return create_entity_domain_from_number(self.domain)

    def __str__(self) -> str:
        return ".".join(str(value) for value in self.as_tuple())

    def to_string(self) -> str:
        return str(self)

    def to_key(self, *, signed: bool = True) -> int:
        return create_key(*self.as_tuple(), signed=signed)

    def to_bytes(self) -> bytes:
        """Eight network-order DIS Entity Type bytes (not an entire PDU)."""
        return struct.pack(">BBHBBBB", *self.as_tuple())

    @classmethod
    def from_string(cls, enum_string: str, separator: str = ".") -> SisoEnum:
        if not separator:
            raise ValueError("Separator must not be empty")
        parts = enum_string.split(separator)
        if len(parts) != 7 or any(re.fullmatch(r"[0-9]+", part.strip()) is None for part in parts):
            raise ValueError(f"Expected seven unsigned decimal fields: {enum_string!r}")
        return cls(*(int(part) for part in parts))

    @classmethod
    def from_key(cls, key: int) -> SisoEnum:
        if not _is_integer(key):
            raise TypeError("Key must be an integer, not a boolean")
        if not -(1 << 63) <= key <= UINT64_MAX:
            raise ValueError("Key must fit a signed or unsigned 64-bit integer")
        return cls(*((key >> shift) & limit for shift, limit in zip(_SHIFTS, _LIMITS, strict=True)))

    @classmethod
    def from_bytes(cls, value: bytes) -> SisoEnum:
        if len(value) != 8:
            raise ValueError("Entity Type wire representation must contain exactly 8 bytes")
        return cls.from_key(int.from_bytes(value, "big"))

    # Source-style spellings. The legacy kind/domain methods retain upstream's
    # actual string-returning numeric-enum behavior, despite its TypeScript annotation.
    toString = to_string
    toKey = to_key
    fromString = from_string
    fromKey = from_key

    def getKind(self) -> str | None:
        return createEntityKindFromNumber(self.kind)

    def getDomain(self) -> str | None:
        return createEntityDomainFromNumber(self.domain)


def createEntityKindFromNumber(value: int | float) -> str | None:
    kind = create_entity_kind_from_number(value)
    return _KIND_JS_NAMES[kind] if kind is not None else None


def createEntityDomainFromNumber(value: int | float) -> str | None:
    domain = create_entity_domain_from_number(value)
    return ENTITY_DOMAIN_DESCRIPTIONS[domain] if domain is not None else None


createEntityKindFromString = create_entity_kind_from_string
createEntityDomainFromString = create_entity_domain_from_string
getEntityKindDescription = get_entity_kind_description
getEntityDomainDescription = get_entity_domain_description
EntityKindDescriptions = ENTITY_KIND_DESCRIPTIONS
EntityDomainDescriptions = ENTITY_DOMAIN_DESCRIPTIONS


class Utils:
    """Source-compatible integer key helper."""

    @staticmethod
    def createKey(
        kind: int,
        domain: int,
        country: int,
        category: int,
        subcategory: int,
        specific: int,
        extra: int,
        *,
        signed: bool = True,
    ) -> int:
        """Pack fields with the same masking and signed-key default as create_key."""
        return create_key(kind, domain, country, category, subcategory, specific, extra, signed=signed)
