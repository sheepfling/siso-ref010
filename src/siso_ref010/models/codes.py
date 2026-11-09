"""Nominal integer types for DIS fields and packed entity keys."""

from typing import NewType, TypeAlias

KindCode = NewType("KindCode", int)
DomainCode = NewType("DomainCode", int)
CountryCode = NewType("CountryCode", int)
CategoryCode = NewType("CategoryCode", int)
SubcategoryCode = NewType("SubcategoryCode", int)
SpecificCode = NewType("SpecificCode", int)
ExtraCode = NewType("ExtraCode", int)
EntityKey = NewType("EntityKey", int)

EntityFieldCode: TypeAlias = (
    KindCode | DomainCode | CountryCode | CategoryCode | SubcategoryCode | SpecificCode | ExtraCode
)
