# Modified work (2026): Python adaptation of TNO-MST/siso-entity-type picker behavior.
# Original copyright 2025 TNO; Apache-2.0. See LICENSE and NOTICE.
"""Display-independent picker state, shared by the native view and tests."""

from __future__ import annotations

from enum import StrEnum

from .api import Choice, Collection, EntityTypeAPI, SearchResults
from .model import SisoEnum


class Field(StrEnum):
    COUNTRY = "country"
    KIND = "kind"
    DOMAIN = "domain"
    CATEGORY = "category"
    SUBCATEGORY = "subcategory"
    SPECIFIC = "specific"
    EXTRA = "extra"


_WIRE_FIELDS = (
    Field.KIND,
    Field.DOMAIN,
    Field.COUNTRY,
    Field.CATEGORY,
    Field.SUBCATEGORY,
    Field.SPECIFIC,
    Field.EXTRA,
)
_COLLECTIONS = dict(zip(Field, Collection, strict=True))
_PARENT_COUNTS = (0, 0, 1, 3, 4, 5, 6)


class PickerState:
    """Atomic validated ID loading and cascading selections.

    Changing country retains kind/domain; changing any other field clears its
    descendants. Re-selecting the same value is a no-op. Unknown in-range codes
    are valid and are retained, even when the catalog has no matching entry.
    """

    def __init__(self, api: EntityTypeAPI | None = None) -> None:
        self.api = api if api is not None else EntityTypeAPI()
        self._entity = SisoEnum(0, 0, 0, 0, 0, 0, 0)
        self.results = SearchResults("", 0, (), None)

    @property
    def entity(self) -> SisoEnum:
        return self._entity

    def load(self, entity_id: str) -> None:
        """Replace all fields only after complete validation succeeds."""
        self._entity = SisoEnum.from_string(entity_id)

    def select(self, field: Field | str, value: int | None) -> None:
        field = Field(field)
        values = list(self.entity.as_tuple())
        index = _WIRE_FIELDS.index(field)
        replacement = 0 if value is None else value
        if value is not None and values[index] == replacement:
            # Still validate bool/float values, which compare equal to integers.
            SisoEnum(*(replacement if i == index else v for i, v in enumerate(values)))
            return
        values[index] = replacement
        start = 3 if field == Field.COUNTRY else index + 1
        for descendant in range(start, 7):
            if descendant != 2:  # Country is independent of kind and domain.
                values[descendant] = 0
        self._entity = SisoEnum(*values)

    def choices(self, field: Field | str) -> tuple[Choice, ...]:
        """Catalog choices plus the current numeric value if it is not listed."""
        field = Field(field)
        count = _PARENT_COUNTS[list(Field).index(field)]
        choices = self.api.choices(_COLLECTIONS[field], *self.entity.as_tuple()[:count]).items
        current = self.entity.as_tuple()[_WIRE_FIELDS.index(field)]
        if not any(choice.value == current for choice in choices):
            label = "Unspecified / not catalogued" if current == 0 else "Unknown (not catalogued)"
            choices = (Choice(current, label), *choices)
        return choices

    def search(self, query: str) -> SearchResults:
        """Case-insensitive substring search, with the upstream three-character minimum."""
        self.results = self.api.search(query) if len(query) >= 3 else SearchResults(query, 0, (), None)
        return self.results

    def select_result(self, index: int) -> None:
        if not 0 <= index < len(self.results.hits):
            raise IndexError("Search result is no longer available")
        self._entity = self.results.hits[index].entity

    def reset(self) -> None:
        self._entity = SisoEnum(0, 0, 0, 0, 0, 0, 0)
        self.results = SearchResults("", 0, (), None)
