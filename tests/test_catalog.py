import json
from pathlib import Path

import pytest

from siso_entity_type import SisoEnum, SisoEnums, create_key
from siso_entity_type.catalog import validate_data

ORACLE = json.loads((Path(__file__).parent / "fixtures/upstream-oracle.json").read_text())


def test_all_upstream_keys_and_descriptions(catalog):
    for key, text, encoded_key, description in ORACLE["all"]:
        entity = SisoEnum.from_key(int(key))
        assert str(entity) == text
        assert str(entity.to_key()) == encoded_key
        assert catalog.get_description_of(entity) == description


def test_upstream_detailed_and_fallback_descriptions(catalog):
    for text, description, qualified, country, kind, domain in ORACLE["detailed"]:
        entity = SisoEnum.from_string(text)
        assert catalog.get_description_of(entity) == description
        assert catalog.get_description_of(entity, True) == qualified
        assert catalog.get_country_name(entity) == country
        assert catalog.get_kind_name(entity) == kind
        assert catalog.get_domain_name(entity) == domain


def test_upstream_collections(catalog):
    for name, args, expected in ORACLE["collections"]:
        assert list(getattr(catalog, name)(*args).items()) == [tuple(row) for row in expected]
    for kind, expected in ORACLE["domains"]:
        assert list(catalog.get_all_domains_of(kind).items()) == [tuple(row) for row in expected]
    assert list(catalog.get_all_domains().items()) == [tuple(row) for row in ORACLE["allDomains"]]


def test_upstream_search(catalog):
    for query, expected in ORACLE["search"]:
        assert catalog.search_description(query) == expected
    assert len(catalog.search_description("")) == 24637
    assert catalog.search_description("F803") == {"1.3.153.6.4.2.0": "F803 Tromp"}


def test_counts_and_original_fixtures(catalog):
    assert (
        catalog.country_count,
        catalog.kind_count,
        catalog.domain_count,
        catalog.category_count,
        catalog.subcategory_count,
    ) == (279, 10, 68, 1867, 24637)
    assert catalog.get_country_name(1) == "Afghanistan (AFG)"
    assert catalog.get_country_name(153) == "Netherlands (NLD)"
    assert len(catalog.get_all_categories_of(1, 4, 153)) == 2
    assert set(catalog.get_all_subcategories_of(1, 4, 153, 5).values()) == {"Hai Lung Class", "Walrus Class"}
    assert len(catalog.get_all_specifics_of(1, 2, 106, 20, 2)) == 4
    assert len(catalog.get_all_extras_of(1, 2, 225, 7, 8, 7)) == 5


@pytest.mark.parametrize(
    "text,short,qualified",
    [
        (
            "3.1.225.15.0.0.0",
            "Coast Guard",
            "Coast Guard / Unknown subcategory 0 / Unknown specific 0 / Unknown extra 0",
        ),
        (
            "2.9.225.2.75.2.1",
            "Impact fuse",
            "Ballistic / Mk-84 / MK-84 Low Drag General Purpose / Impact fuse",
        ),
        (
            "2.9.225.2.75.2.0",
            "MK-84 Low Drag General Purpose",
            "Ballistic / Mk-84 / MK-84 Low Drag General Purpose",
        ),
        ("2.9.225.2.75.88.0", "Mk-84", "Ballistic / Mk-84 / Unknown specific 88 / Unknown extra 0"),
        ("1.2.13.1.1.2.0", "F/A-18B", "Fighter/Air Defense / McDonnell-Douglas F/A-18 Hornet / F/A-18B"),
    ],
)
def test_original_description_examples(catalog, text, short, qualified):
    entity = SisoEnum.from_string(text)
    assert catalog.get_description_of(entity) == short
    assert catalog.get_description_of(entity, True) == qualified


def test_initialization_is_atomic_replacement():
    key = str(create_key(1, 1, 153, 2, 0, 0, 0))
    data = {"countries": {}, "domains": {}, "subcategories": {}, "categories": {key: "Old"}}
    catalog = SisoEnums(data)
    entity = SisoEnum.from_key(int(key))
    assert catalog.get_description_of(entity, True).startswith("Old")
    with pytest.raises(ValueError):
        catalog.initialize({"bad": 1})
    assert catalog.get_description_of(entity) == "Old"
    data["categories"][key] = "New"
    catalog.initialize(data)
    assert catalog.get_description_of(entity, True).startswith("New")
    copy = catalog.get_all_categories_of(1, 1, 153)
    copy[2] = "Mutated"
    assert catalog.get_category_name(entity) == "New"
    catalog.initialize({"countries": {}, "domains": {}, "subcategories": {}, "categories": {}})
    assert catalog.get_description_of(entity) == "-"


def test_country_overlay_follows_upstream_insertion_order():
    specific = str(create_key(1, 1, 153, 2, 0, 0, 0))
    generic = str(create_key(1, 1, 0, 2, 0, 0, 0))
    for categories, expected in [
        ({specific: "Specific", generic: "Generic"}, "Generic"),
        ({generic: "Generic", specific: "Specific"}, "Specific"),
    ]:
        catalog = SisoEnums({"countries": {}, "domains": {}, "subcategories": {}, "categories": categories})
        assert catalog.get_all_categories_of(1, 1, 153)[2] == expected
        # Description fallback prioritizes the country-specific key, independently of collection ordering.
        assert catalog.get_description_of(SisoEnum.from_key(int(specific))) == "Specific"


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {},
        {"countries": []},
        {"countries": {}, "domains": {}, "subcategories": {}, "categories": {"x": "bad"}},
        {"countries": {}, "domains": {}, "subcategories": {}, "categories": {"0": 1}},
    ],
)
def test_invalid_data(value):
    with pytest.raises(ValueError):
        validate_data(value)


def test_empty_catalog():
    catalog = SisoEnums()
    assert catalog.kind_count == 0
    assert catalog.get_kind_name(1) == "Unknown kind 1"
    assert catalog.get_description_of(SisoEnum(0, 0, 0, 0, 0, 0, 0)) == "-"


def test_noncanonical_keys():
    for key in ["00", "-0", "18446744073709551616", "-9223372036854775809"]:
        with pytest.raises(ValueError):
            validate_data({"countries": {}, "domains": {}, "subcategories": {}, "categories": {key: "x"}})
