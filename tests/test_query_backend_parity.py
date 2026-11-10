from collections.abc import Callable, Mapping
from typing import cast

import pytest

from siso_ref010 import SisoRef010API
from siso_ref010.catalog import ReferenceCatalog
from siso_ref010.parsing import EntityTypeXmlParser
from siso_ref010.query_backend import EntityFieldFilters, EntityQueryRequest


def _dynamic_query(api: SisoRef010API, filters: Mapping[str, int | str]) -> object:
    query = cast(Callable[..., object], api.query_entities)
    return query(**filters)


@pytest.mark.parametrize(
    "values",
    [
        (1, 2, 225, 4, 5, 6, 7),
        (None, 0, None, 0, None, 0, None),
        (None, None, None, None, None, None, None),
    ],
)
def test_query_fields_are_named_and_keep_tuple_behavior(values: tuple[int | None, ...]) -> None:
    request = EntityQueryRequest(*values, text="demo", limit=3, offset=2)
    fields = request.fields

    assert isinstance(fields, EntityFieldFilters)
    assert fields == values
    assert tuple(fields) == values
    assert hash(fields) == hash(values)
    assert (
        fields.entity_kind,
        fields.domain,
        fields.country,
        fields.category,
        fields.subcategory,
        fields.specific,
        fields.extra,
    ) == values
    with pytest.raises(AttributeError):
        attribute = "country"
        setattr(fields, attribute, 153)


def test_cold_and_warmed_queries_match_for_source_records() -> None:
    cold = SisoRef010API.bundled()
    warm = SisoRef010API.bundled()
    warm.warmup()
    cases = [
        {},
        {"country": 153, "text": "Tromp"},
        {"entity_kind": 1, "domain": 1, "country": 153, "category": 6},
        {"subcategory": 1, "offset": 3, "limit": 7},
        {"country": 0, "limit": 0},
        {"text": "KIND 1", "limit": 3},
    ]
    for case in cases:
        assert _dynamic_query(cold, case) == _dynamic_query(warm, case)
        assert _dynamic_query(cold, case) == _dynamic_query(warm, case)


def test_ranges_and_cross_references_match() -> None:
    xml = (
        '<ebv title="fixture" date="2026-01-01">'
        '<enum uid="7" name="table"><enumrow value="8" description="xref"/></enum>'
        '<cet name="Entity Types"><entity kind="1" domain="1" country="0">'
        '<category value="2"><subcategory_range value_min="4" value_max="6" description="range">'
        '<specific value="5" description="child"/></subcategory_range>'
        '<subcategory_xref xref="7"/></category></entity></cet></ebv>'
    )
    standard = EntityTypeXmlParser.from_string(xml)
    cold = SisoRef010API(ReferenceCatalog(standard))
    warm = SisoRef010API(ReferenceCatalog(standard))
    warm.warmup()
    for case in (
        {},
        {"country": 153, "subcategory": 5},
        {"subcategory": 8},
        {"text": "xref"},
        {"specific": 5},
    ):
        assert _dynamic_query(cold, case) == _dynamic_query(warm, case)
