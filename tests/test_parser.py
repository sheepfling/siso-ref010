import hashlib
import pathlib
from datetime import date
from pathlib import Path

import pytest

from siso_ref010.catalog import ReferenceCatalog
from siso_ref010.models.codes import CountryCode, KindCode
from siso_ref010.models.entity import EntityType
from siso_ref010.models.standard import EntityTypeStandard
from siso_ref010.parsing import EntityTypeXmlParser, ParseError

DATA_DIR = Path(__file__).parents[1] / "src/siso_ref010/data"
FIXTURES = DATA_DIR / "standards"


@pytest.fixture(scope="module")
def parsed() -> EntityTypeStandard:
    return EntityTypeXmlParser.from_file(FIXTURES / "v37.xml")


def test_v37_xml_metadata_and_counts(parsed: EntityTypeStandard) -> None:
    catalog = ReferenceCatalog(parsed)
    assert len(parsed.enumerations) == 535
    assert len(parsed.entity_types) == 451
    assert (
        catalog.country_count,
        catalog.kind_count,
        catalog.domain_count,
        catalog.category_count,
        catalog.subcategory_count,
    ) == (279, 11, 68, 1889, 25473)
    assert parsed.title == "SISO-REF-010-v37"
    assert parsed.date == date(2026, 5, 25)


@pytest.mark.parametrize(
    "path,blob",
    [
        (FIXTURES / "v37.xml", "eaafe0b868e5fe6b3497c915226f312ca9853c242fae11d2f6afcbfb53c8be8c"),
        (DATA_DIR / "SISO-REF-010.xsd", "4f6cb195ac133daf745e3fd51e070534c99fc2cb5b53a8dc9a58e8c9e49327ab"),
    ],
)
def test_pinned_fixture_hashes(path: pathlib.Path, blob: str) -> None:
    value = path.read_bytes()
    assert hashlib.sha256(value).hexdigest() == blob


def test_v37_reference_examples(parsed: EntityTypeStandard) -> None:
    catalog = ReferenceCatalog(parsed)
    assert catalog.get_country_name(CountryCode(153)) == "Netherlands (NLD)"
    assert catalog.get_kind_name(KindCode(1)) == "Platform"
    assert catalog.get_domain_name(EntityType(1, 1, 0, 0, 0, 0, 0)) == "Land"
    assert catalog.get_domain_name(EntityType(3, 2, 0, 0, 0, 0, 0)) == "Air"
    assert catalog.get_category_name(EntityType(1, 1, 0, 81, 0, 0, 0)) == "Car"
    for specific, extra, text in [
        (7, 1, "MC-12S EMARSS-S"),
        (7, 0, "MC-12W Liberty"),
        (0, 0, "Beechcraft Super King AIR 200/B200"),
    ]:
        entity = EntityType(1, 2, 225, 7, 8, specific, extra)
        if extra:
            assert catalog.get_extra_name(entity) == text
        elif specific:
            assert catalog.get_specific_name(entity) == text
        else:
            assert catalog.get_subcategory_name(entity) == text


@pytest.mark.parametrize(
    "xml",
    [
        "<bad/>",
        "<ebv>",
        '<!DOCTYPE ebv [<!ENTITY a "abc">]><ebv/>',
        '<ebv><cet name="Entity Types"><entity kind="1" domain="x" country="0"/></cet></ebv>',
        '<ebv><enum uid="29"><enumrow value="x" description="A"/></enum></ebv>',
    ],
)
def test_reject_invalid_or_unsafe_xml(xml: str) -> None:
    with pytest.raises(ParseError):
        EntityTypeXmlParser.from_string(xml)


MINI = """<ebv xmlns="urn:test" title="Test" date="2026-01-01">
<enum uid="29" name="Country"><enumrow value="153" description="Netherlands"/></enum>
<enum uid="8" name="Platform Domain" applicability="1,3-5"><enumrow value="1" description="Land"/></enum>
<cet name="Entity Types"><entity kind="1" domain="1" country="153"><category value="2" description="A">
<subcategory value="3" description="B"><specific value="4" description="C">
<extra value="5" description="D" deprecated="true"/>
</specific></subcategory></category></entity></cet></ebv>"""


def test_singletons_namespace_qualification_and_deprecated() -> None:
    parsed = EntityTypeXmlParser.from_string(MINI)
    catalog = ReferenceCatalog(parsed)
    assert catalog.country_count == 1
    assert catalog.domain_count == 4
    key = EntityType(1, 1, 153, 2, 3, 4, 5).to_key()
    assert catalog.get_description_of(EntityType.from_key(key)) == "D"
    assert catalog.get_description_of(EntityType.from_key(key), fully_qualified=True) == "A / B / C / D"


def test_legacy_comprehensive_entity_table_name_is_loaded() -> None:
    parsed = EntityTypeXmlParser.from_string(
        '<ebv><cet uid="30" name="Comprehensive Entity Types">'
        '<entity kind="1" domain="1" country="225">'
        '<category value="2" description="Legacy category"/>'
        "</entity></cet></ebv>"
    )
    assert parsed.entity_table is not None
    assert parsed.entity_table.get("name") == "Comprehensive Entity Types"
    assert ReferenceCatalog(parsed).get_category_name(EntityType(1, 1, 225, 2, 0, 0, 0)) == "Legacy category"


def test_load_file_and_preserve_metadata(tmp_path: pathlib.Path) -> None:
    source = tmp_path / "input.xml"
    source.write_text(MINI, encoding="utf-8")
    parsed = EntityTypeXmlParser.from_file(source)
    assert parsed.title == "Test"
    assert parsed.date == date(2026, 1, 1)
    assert ReferenceCatalog(parsed).get_country_name(CountryCode(153)) == "Netherlands"


def test_empty_and_missing_description() -> None:
    parsed = EntityTypeXmlParser.from_string("<ebv/>")
    assert parsed.enumerations == ()
    assert parsed.entity_types == ()
    entry = EntityTypeXmlParser.from_string('<ebv><enum uid="29"><enumrow value="1"/></enum></ebv>')
    assert entry.enumerations[0].entries[0].description is None


def test_missing_and_wildcard_applicability() -> None:
    no_applicability = (
        '<ebv><enum uid="8" name="Platform Domain"><enumrow value="1" description="A"/></enum></ebv>'
    )
    assert ReferenceCatalog(EntityTypeXmlParser.from_string(no_applicability)).domain_count == 0
    wildcard = (
        '<ebv><cet name="Entity Types"><entity kind="3" domain="0" country="0">'
        '<category value="2" description="A"/></entity></cet></ebv>'
    )
    parsed = EntityTypeXmlParser.from_string(wildcard)
    catalog = ReferenceCatalog(parsed)
    assert catalog.get_category_name(EntityType(3, 0, 0, 2, 0, 0, 0)) == "A"
