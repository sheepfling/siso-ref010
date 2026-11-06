# Modified work (2026): Python adaptation of TNO-MST/siso-entity-type.
# Original copyright 2025 TNO; Apache-2.0. See LICENSE and NOTICE.
"""Compatibility map for callers porting upstream LongKeyMap usage.

Python integer-key dictionaries suffice for new code. Keys are integers, not
long.js objects. Returned collections are snapshots, as in the upstream helper.
"""

from collections.abc import Callable
from typing import Generic, TypeVar

V = TypeVar("V")


class LongKeyMap(Generic[V]):
    def __init__(self) -> None:
        self._map: dict[int, V] = {}

    def set(self, key: int, value: V) -> None:
        self._map[key] = value

    def get(self, key: int) -> V | None:
        return self._map.get(key)

    def has(self, key: int) -> bool:
        return key in self._map

    def delete(self, key: int) -> bool:
        if key in self._map:
            del self._map[key]
            return True
        return False

    def clear(self) -> None:
        self._map.clear()

    def keys(self) -> list[int]:
        return list(self._map.keys())

    def values(self) -> list[V]:
        return list(self._map.values())

    def entries(self) -> list[tuple[int, V]]:
        return list(self._map.items())

    def for_each(self, callback: Callable[[V, int, "LongKeyMap[V]"], None]) -> None:
        """Call for each entry; structural mutation during iteration is unsupported."""
        for key, value in self._map.items():
            callback(value, key, self)

    @property
    def size(self) -> int:
        return len(self._map)

    forEach = for_each
