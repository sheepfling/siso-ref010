import hashlib
import json
from pathlib import Path

import pytest

from siso_entity_type import ParseError, SisoEnumsFactory, SisoEnumsParser, create_key

FIXTURES = Path(__file__).parent / "fixtures"
DATA = Path(__file__).parents[1] / "src/siso_entity_type/data/siso-enums.json"


@pytest.fixture(scope="module")
def parsed():
    return SisoEnumsParser.from_file(FIXTURES / "siso-ref-010-v35.xml")


def test_full_xml_to_json_parity(parsed):
    assert parsed.to_data() == json.loads(DATA.read_text())
    # Upstream's exact output order is preserved, not just unordered map equality.
    for name, entries in json.loads(DATA.read_text()).items():
        assert list(parsed.to_data()[name].items()) == list(entries.items())
    assert (
        parsed.country_count,
        parsed.kind_count,
        parsed.domain_count,
        parsed.category_count,
        parsed.subcategory_count,
    ) == (279, 10, 68, 1867, 24637)
    assert parsed.title == "SISO-REF-010-v35"
    assert parsed.date == "2025-04-27"
    assert "Reprinted with permission from SISO Inc." in parsed.copyright_notice


@pytest.mark.parametrize(
    "path,blob",
    [
        (FIXTURES / "siso-ref-010-v35.xml", "0ad0a1af71adfb03ac0049802d6376f1cbd7c9ed"),
        (DATA, "674b445bff0feab409c8bee1b24873dc33a4716c"),
    ],
)
def test_pinned_fixture_hashes(path, blob):
    value = path.read_bytes()
    assert hashlib.sha1(b"blob " + str(len(value)).encode() + b"\0" + value).hexdigest() == blob


def test_upstream_parser_examples(parsed):
    assert parsed.get_country(create_key(0, 0, 153, 0, 0, 0, 0)) == "Netherlands (NLD)"
    assert parsed.get_kind(create_key(1, 0, 0, 0, 0, 0, 0)) == "Platform"
    assert parsed.get_domain(create_key(1, 1, 0, 0, 0, 0, 0)) == "Land"
    assert parsed.get_domain(create_key(3, 2, 0, 0, 0, 0, 0)) == "Air"
    assert parsed.get_category(create_key(1, 1, 0, 81, 0, 0, 0)) == "Car"
    assert parsed.get_category(create_key(3, 2, 0, 200, 0, 0, 0)) == "Bird"
    for specific, extra, text in [
        (7, 1, "MC-12S EMARSS-S"),
        (7, 0, "MC-12W Liberty"),
        (0, 0, "Beechcraft Super King AIR 200/B200"),
    ]:
        assert parsed.get_subcategory(create_key(1, 2, 225, 7, 8, specific, extra)) == text


@pytest.mark.parametrize(
    "xml",
    [
        "<bad/>",
        "<ebv>",
        '<!DOCTYPE ebv [<!ENTITY a "abc">]><ebv/>',
        '<ebv><cet><entity kind="1" domain="x" country="0"/></cet></ebv>',
        '<ebv><enum uid="29"><enumrow value="x" description="A"/></enum></ebv>',
    ],
)
def test_reject_invalid_or_unsafe_xml(xml):
    with pytest.raises(ParseError):
        SisoEnumsParser.from_string(xml)


MINI = """<ebv xmlns="urn:test" title="Test" date="2026-01-01">
<enum uid="29"><enumrow value="153" description="Netherlands"/></enum>
<enum uid="8" applicability="1,3-5"><enumrow value="1" description="Land"/></enum>
<cet><entity kind="1" domain="1" country="153"><category value="2" description="A">
<subcategory value="3" description="B"><specific value="4" description="C">
<extra value="5" description="D" deprecated="true"/>
</specific></subcategory></category></entity></cet></ebv>"""


def test_singletons_namespace_qualification_and_deprecated():
    parsed = SisoEnumsFactory.createFromString(MINI)
    assert parsed.countryCount == 1
    assert parsed.domainCount == 4
    key = create_key(1, 1, 153, 2, 3, 4, 5)
    assert parsed.getSubcategory(key) == "D"
    qualified = SisoEnumsParser.from_string(MINI, qualified=True, delimiter=" > ")
    assert qualified.get_subcategory(key) == "A > B > C > D"
    assert SisoEnumsParser.from_string(parsed.to_string()).to_data() == parsed.to_data()


def test_write_and_load(tmp_path, parsed):
    result = SisoEnumsFactory.write_output(parsed, tmp_path / "nested")
    assert json.loads(result.read_text()) == parsed.to_data()
    source = tmp_path / "input.xml"
    source.write_text(MINI)
    assert SisoEnumsFactory.create_from_file(source).title == "Test"


def test_empty_and_missing_description():
    assert SisoEnumsParser.from_string("<ebv/>").to_data() == {
        "subcategories": {},
        "categories": {},
        "countries": {},
        "domains": {},
    }
    with pytest.raises(ParseError):
        SisoEnumsParser.from_string('<ebv><enum uid="29"><enumrow value="1"/></enum></ebv>')


def test_missing_and_wildcard_applicability():
    no_applicability = '<ebv><enum uid="8"><enumrow value="1" description="A"/></enum></ebv>'
    assert SisoEnumsParser.from_string(no_applicability).domain_count == 0
    wildcard = '<ebv><enum uid="472" applicability="3.X"><enumrow value="2" description="A"/></enum></ebv>'
    parsed = SisoEnumsParser.from_string(wildcard)
    assert parsed.get_category(create_key(3, 0, 0, 2, 0, 0, 0)) == "A"
