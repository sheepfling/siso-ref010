from siso_ref010 import EntityTypeXmlParser, ReferenceCatalog, SisoRef010API


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
        assert cold.query_entities(**case) == warm.query_entities(**case)
        assert cold.query_entities(**case) == warm.query_entities(**case)


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
        assert cold.query_entities(**case) == warm.query_entities(**case)
