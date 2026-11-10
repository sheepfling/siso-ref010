import pytest

from siso_ref010 import EntityType, SisoRef010API
from siso_ref010.catalog import ReferenceCatalog
from siso_ref010.parsing.xml import EntityTypeXmlParser
from siso_ref010.projection import _field_values


def test_search_uses_the_deepest_effective_description_for_zero_padded_codes() -> None:
    standard = EntityTypeXmlParser.from_string(
        '<ebv><enum uid="30" name="Entity Kind">'
        '<enumrow value="1" description="Platform"/></enum>'
        '<cet><entity kind="1" domain="1" country="1">'
        '<category value="2" description="Parent category">'
        '<subcategory value="0" description="Explicit zero subcategory"/>'
        "</category></entity></cet></ebv>"
    )
    catalog = ReferenceCatalog(standard)
    api = SisoRef010API(catalog)
    code = "1.1.1.2.0.0.0"

    assert catalog.get_description_of(EntityType.from_string(code)) == "Explicit zero subcategory"
    assert catalog.search_descriptions("Parent category") == {code: ("Explicit zero subcategory",)}
    assert catalog.search_description("Parent category") == {code: "Explicit zero subcategory"}

    hit = api.search("Parent category").hits[0]
    assert hit.entity == EntityType.from_string(code)
    assert hit.description == "Explicit zero subcategory"
    assert hit.candidate_descriptions == ()
    assert not hit.ambiguous


def test_applicability_range_rejects_more_than_two_bounds() -> None:
    with pytest.raises(ValueError) as error:
        _field_values("1-3-4")

    assert getattr(error.value, "code", None) == "invalid_applicability_range"
