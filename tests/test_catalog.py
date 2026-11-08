import pytest

from siso_ref010 import (
    CountryCode,
    EntityType,
    EntityTypeCatalog,
    EntityTypeStandard,
    EntityTypeXmlParser,
    KindCode,
)


def _catalog_xml(entities: str, *, title: str = "Test") -> EntityTypeStandard:
    return EntityTypeXmlParser.from_string(
        f'<ebv title="{title}"><cet name="Entity Types">{entities}</cet></ebv>'
    )


def test_catalog_search(catalog):
    assert len(catalog.search_description("")) == 27323
    assert catalog.search_description("F803") == {"1.3.153.6.4.2.0": "F803 Tromp"}


def test_v37_catalog_counts_and_examples(catalog):
    assert (
        catalog.country_count,
        catalog.kind_count,
        catalog.domain_count,
        catalog.category_count,
        catalog.subcategory_count,
    ) == (279, 11, 68, 1889, 25473)
    assert catalog.get_country_name(CountryCode(1)) == "Afghanistan (AFG)"
    assert catalog.get_country_name(CountryCode(153)) == "Netherlands (NLD)"
    assert len(catalog.get_all_categories_of(EntityType(1, 4, 153, 0, 0, 0, 0))) == 2
    assert set(catalog.get_all_subcategories_of(EntityType(1, 4, 153, 5, 0, 0, 0)).values()) == {
        "Hai Lung Class",
        "Walrus Class",
    }
    assert len(catalog.get_all_specifics_of(EntityType(1, 2, 106, 20, 2, 0, 0))) == 3
    assert len(catalog.get_all_extras_of(EntityType(1, 2, 225, 7, 8, 7, 0))) == 4


@pytest.mark.parametrize(
    "text,short,qualified",
    [
        (
            "1.1.0.81.0.0.0",
            "Car",
            "Car / Unknown subcategory 0 / Unknown specific 0 / Unknown extra 0",
        ),
        (
            "2.9.225.2.75.2.1",
            "Impact fuse",
            "Ballistic / Mk-84 / MK-84 Low Drag General Purpose / Impact fuse",
        ),
        (
            "2.9.225.2.75.2.0",
            "MK-84 Low Drag General Purpose",
            "Ballistic / Mk-84 / MK-84 Low Drag General Purpose / Unknown extra 0",
        ),
        ("2.9.225.2.75.88.0", "Mk-84", "Ballistic / Mk-84 / Unknown specific 88 / Unknown extra 0"),
        (
            "1.2.13.1.1.2.0",
            "F/A-18B",
            "Fighter/Air Defense / McDonnell-Douglas F/A-18 Hornet / F/A-18B / Unknown extra 0",
        ),
    ],
)
def test_original_description_examples(catalog, text, short, qualified):
    entity = EntityType.from_string(text)
    assert catalog.get_description_of(entity) == short
    assert catalog.get_description_of(entity, True) == qualified


def test_initialization_is_atomic_replacement():
    old = _catalog_xml(
        '<entity kind="1" domain="1" country="153"><category value="2" description="Old"/></entity>'
    )
    new = _catalog_xml(
        '<entity kind="1" domain="1" country="153"><category value="2" description="New"/></entity>'
    )
    catalog = EntityTypeCatalog(old)
    entity = EntityType(1, 1, 153, 2, 0, 0, 0)
    assert catalog.get_description_of(entity, True).startswith("Old")
    with pytest.raises(ValueError):
        catalog.initialize({"bad": 1})
    assert catalog.get_description_of(entity) == "Old"
    catalog.initialize(new)
    assert catalog.get_description_of(entity, True).startswith("New")
    prefix = EntityType(1, 1, 153, 0, 0, 0, 0)
    copy = catalog.get_all_categories_of(prefix)
    copy[2] = "Mutated"
    assert catalog.get_category_name(entity) == "New"
    catalog.initialize(EntityTypeXmlParser.from_string("<ebv/>"))
    assert catalog.get_description_of(entity) == "-"


def test_country_overlay_follows_source_order():
    prefix = EntityType(1, 1, 153, 0, 0, 0, 0)
    specific = (
        '<entity kind="1" domain="1" country="153"><category value="2" description="Specific"/></entity>'
    )
    generic = '<entity kind="1" domain="1" country="0"><category value="2" description="Generic"/></entity>'
    for categories, expected in [
        (specific + generic, "Generic"),
        (generic + specific, "Specific"),
    ]:
        catalog = EntityTypeCatalog(_catalog_xml(categories))
        assert catalog.get_all_categories_of(prefix)[2] == expected
        # Description fallback prioritizes the country-specific key, independently of collection ordering.
        entity = EntityType(1, 1, 153, 2, 0, 0, 0)
        assert catalog.get_description_of(entity) == "Specific"


def test_empty_catalog():
    catalog = EntityTypeCatalog()
    assert catalog.kind_count == 0
    assert catalog.get_kind_name(KindCode(1)) == "Unknown kind 1"
    assert catalog.get_description_of(EntityType(0, 0, 0, 0, 0, 0, 0)) == "-"
