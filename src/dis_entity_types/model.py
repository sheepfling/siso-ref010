"""DIS entity fields and their exact 64-bit key representation.

The Python model validates wire fields rather than silently coercing malformed input.
``create_key`` packs each field at its defined wire width.
"""

from __future__ import annotations

import re
import struct
from collections.abc import Mapping
from enum import IntEnum
from types import MappingProxyType
from typing import Annotated, Final, NoReturn, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .codes import (
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
from .errors import EntityTypeTypeError, EntityTypeValueError


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
    C2_LOGICAL_OBJECT = 10


class EntityDomain(IntEnum):
    """Platform domains. Munition and supply domains use different code sets."""

    OTHER = 0
    LAND = 1
    AIR = 2
    SURFACE = 3
    SUBSURFACE = 4
    SPACE = 5


_ENTITY_KIND_DESCRIPTIONS: Final = MappingProxyType(
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
                "Command and Control (C2) Logical Object",
            ),
            strict=True,
        )
    )
)
_ENTITY_DOMAIN_DESCRIPTIONS: Final = MappingProxyType(
    dict(zip(EntityDomain, ("Other", "Land", "Air", "Surface", "Subsurface", "Space"), strict=True))
)

_SHIFTS: Final = (56, 48, 32, 24, 16, 8, 0)
_LIMITS: Final = (255, 255, 65535, 255, 255, 255, 255)
_NAMES: Final = ("kind", "domain", "country", "category", "subcategory", "specific", "extra")
_FIELD_LIMITS: Final[Mapping[str, int]] = MappingProxyType(dict(zip(_NAMES, _LIMITS, strict=True)))
_UINT64_MAX: Final = (1 << 64) - 1


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
            for kind, text in _ENTITY_KIND_DESCRIPTIONS.items()
            if text.lower().replace("/", "").replace(" ", "") == normalized
        ),
        None,
    )


def create_entity_domain_from_string(name: str) -> EntityDomain | None:
    return next(
        (domain for domain, text in _ENTITY_DOMAIN_DESCRIPTIONS.items() if text.lower() == name.lower()), None
    )


def get_entity_kind_description(kind: int) -> str | None:
    value = create_entity_kind_from_number(kind)
    return _ENTITY_KIND_DESCRIPTIONS.get(value) if value is not None else None


def get_entity_domain_description(domain: int) -> str | None:
    value = create_entity_domain_from_number(domain)
    return _ENTITY_DOMAIN_DESCRIPTIONS.get(value) if value is not None else None


def _is_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def create_key(
    *,
    kind: KindCode,
    domain: DomainCode,
    country: CountryCode,
    category: CategoryCode,
    subcategory: SubcategoryCode,
    specific: SpecificCode,
    extra: ExtraCode,
    signed: bool = True,
) -> EntityKey:
    """Pack named integer fields into the signed 64-bit key representation.

    Use ``EntityType`` when field bounds must be validated. No floats, strings or
    booleans are implicitly coerced. Pass ``signed=False`` for an unsigned key.
    """
    return _pack_key((kind, domain, country, category, subcategory, specific, extra), signed=signed)


def _pack_key(values: tuple[int, ...], *, signed: bool = True) -> EntityKey:
    key = 0
    for name, value, shift, limit in zip(
        _NAMES,
        values,
        _SHIFTS,
        _LIMITS,
        strict=True,
    ):
        if not _is_integer(value):
            raise EntityTypeTypeError(
                "Entity fields must be integers, not booleans",
                code="invalid_field_type",
                context={"field": name, "value": value, "expected": "integer"},
            )
        key |= (value & limit) << shift
    return EntityKey(key - (1 << 64) if signed and key >= (1 << 63) else key)


class EntityType(BaseModel):
    """Frozen Pydantic model for the seven bounded DIS Entity Type fields."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    kind: Annotated[KindCode, Field(ge=0, le=255)]
    domain: Annotated[DomainCode, Field(ge=0, le=255)]
    country: Annotated[CountryCode, Field(ge=0, le=65535)]
    category: Annotated[CategoryCode, Field(ge=0, le=255)]
    subcategory: Annotated[SubcategoryCode, Field(ge=0, le=255)]
    specific: Annotated[SpecificCode, Field(ge=0, le=255)]
    extra: Annotated[ExtraCode, Field(ge=0, le=255)]

    def __init__(self, *args: object, **data: object) -> None:
        """Keep the established positional constructor and validate fields with Pydantic."""
        if len(args) > len(_NAMES):
            raise TypeError(f"EntityType takes at most {len(_NAMES)} positional arguments")
        values = dict(data)
        for name, value in zip(_NAMES, args, strict=False):
            if name in values:
                raise TypeError(f"EntityType got multiple values for field {name!r}")
            values[name] = value
        try:
            super().__init__(**values)
        except ValidationError as exc:
            _raise_entity_validation_error(exc)

    def as_tuple(self) -> tuple[EntityFieldCode, ...]:
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
        """Return a platform-domain enum when defined; otherwise use catalog names."""
        return create_entity_domain_from_number(self.domain)

    def __str__(self) -> str:
        return ".".join(str(value) for value in self.as_tuple())

    def to_string(self) -> str:
        return str(self)

    def to_key(self, *, signed: bool = True) -> EntityKey:
        return _pack_key(self.as_tuple(), signed=signed)

    def to_bytes(self) -> bytes:
        """Eight network-order DIS Entity Type bytes (not an entire PDU)."""
        return struct.pack(">BBHBBBB", *self.as_tuple())

    @classmethod
    def from_string(cls, enum_string: str, separator: str = ".") -> EntityType:
        if not separator:
            raise EntityTypeValueError(
                "Separator must not be empty",
                code="empty_separator",
                context={"separator": separator},
            )
        parts = enum_string.split(separator)
        if len(parts) != 7 or any(re.fullmatch(r"[0-9]+", part.strip()) is None for part in parts):
            raise EntityTypeValueError(
                f"Expected seven unsigned decimal fields: {enum_string!r}",
                code="invalid_entity_string",
                context={"value": enum_string, "separator": separator, "expected_fields": 7},
            )
        return cls(*(int(part) for part in parts))

    @classmethod
    def from_key(cls, key: int) -> EntityType:
        if not _is_integer(key):
            raise EntityTypeTypeError(
                "Key must be an integer, not a boolean",
                code="invalid_key_type",
                context={"value": key, "expected": "integer"},
            )
        if not -(1 << 63) <= key <= _UINT64_MAX:
            raise EntityTypeValueError(
                "Key must fit a signed or unsigned 64-bit integer",
                code="key_out_of_range",
                context={"value": key, "minimum": -(1 << 63), "maximum": _UINT64_MAX},
            )
        return cls(*((key >> shift) & limit for shift, limit in zip(_SHIFTS, _LIMITS, strict=True)))

    @classmethod
    def from_bytes(cls, value: bytes) -> EntityType:
        if len(value) != 8:
            raise EntityTypeValueError(
                "Entity Type wire representation must contain exactly 8 bytes",
                code="invalid_wire_length",
                context={"length": len(value), "expected_length": 8},
            )
        return cls.from_key(int.from_bytes(value, "big"))


class EntityTypePrefix(BaseModel):
    """A validated, contiguous prefix of the seven DIS entity fields."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    kind: Annotated[KindCode | None, Field(ge=0, le=255)] = None
    domain: Annotated[DomainCode | None, Field(ge=0, le=255)] = None
    country: Annotated[CountryCode | None, Field(ge=0, le=65535)] = None
    category: Annotated[CategoryCode | None, Field(ge=0, le=255)] = None
    subcategory: Annotated[SubcategoryCode | None, Field(ge=0, le=255)] = None
    specific: Annotated[SpecificCode | None, Field(ge=0, le=255)] = None
    extra: Annotated[ExtraCode | None, Field(ge=0, le=255)] = None

    def __init__(self, **data: object) -> None:
        super().__init__(**data)

    @model_validator(mode="after")
    def validate_contiguous_fields(self) -> Self:
        gap = False
        for value in self.as_tuple():
            if value is None:
                gap = True
            elif gap:
                raise ValueError("entity prefix fields must be contiguous from kind")
        return self

    def as_tuple(self) -> tuple[EntityFieldCode | None, ...]:
        return (
            self.kind,
            self.domain,
            self.country,
            self.category,
            self.subcategory,
            self.specific,
            self.extra,
        )

    @property
    def values(self) -> tuple[EntityFieldCode, ...]:
        return tuple(value for value in self.as_tuple() if value is not None)

    @property
    def depth(self) -> int:
        return len(self.values)

    def to_entity(self) -> EntityType:
        return EntityType(*self.values, *((0,) * (7 - self.depth)))

    @classmethod
    def from_values(cls, values: tuple[int, ...]) -> Self:
        """Build a prefix from an ordered CLI or wire-field sequence."""
        if len(values) > len(_NAMES):
            raise EntityTypeValueError(
                f"an entity prefix can contain at most {len(_NAMES)} fields",
                code="invalid_prefix_length",
                context={"received": len(values), "maximum": len(_NAMES)},
            )
        return cls.model_validate(dict(zip(_NAMES, values, strict=False)))


def _raise_entity_validation_error(error: ValidationError) -> NoReturn:
    """Keep the public TypeError/ValueError boundary while Pydantic checks fields."""
    detail = error.errors()[0]
    field = str(detail["loc"][0]) if detail["loc"] else "entity"
    value = detail.get("input")
    if detail["type"] == "int_type":
        raise EntityTypeTypeError(
            f"{field} must be an integer, not a boolean",
            code="invalid_field_type",
            context={"field": field, "value": value, "expected": "integer"},
        ) from error
    if detail["type"] in {"greater_than_equal", "less_than_equal"} and field in _FIELD_LIMITS:
        maximum = _FIELD_LIMITS[field]
        raise EntityTypeValueError(
            f"{field} must be in 0..{maximum}, got {value}",
            code="field_out_of_range",
            context={"field": field, "value": value, "minimum": 0, "maximum": maximum},
        ) from error
    raise error
