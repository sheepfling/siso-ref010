"""Stable top-level API for SISO-REF-010 and DIS Entity Type lookups."""

from ._version import __version__
from .api import BundledEdition, BundledStandards, Collection, SisoRef010API, decode_key, encode_entity
from .errors import SisoRef010Error, SisoRef010IndexError, SisoRef010TypeError, SisoRef010ValueError
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
from .models.entity import EntityType, EntityTypePrefix

__all__ = [
    "__version__",
    "CategoryCode",
    "BundledEdition",
    "BundledStandards",
    "Collection",
    "CountryCode",
    "DomainCode",
    "EntityFieldCode",
    "EntityKey",
    "EntityType",
    "EntityTypePrefix",
    "ExtraCode",
    "KindCode",
    "SisoRef010API",
    "SisoRef010Error",
    "SisoRef010IndexError",
    "SisoRef010TypeError",
    "SisoRef010ValueError",
    "SpecificCode",
    "SubcategoryCode",
    "decode_key",
    "encode_entity",
]
