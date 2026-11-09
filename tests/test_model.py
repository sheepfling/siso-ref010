import random

import pytest

from siso_ref010 import (
    CategoryCode,
    CountryCode,
    DomainCode,
    EntityDomain,
    EntityKind,
    EntityType,
    ExtraCode,
    KindCode,
    SisoRef010ValueError,
    SpecificCode,
    SubcategoryCode,
)
from siso_ref010.models.entity import (
    create_entity_domain_from_number,
    create_entity_domain_from_string,
    create_entity_kind_from_number,
    create_entity_kind_from_string,
    create_key,
)
from siso_ref010.models.standard import ReferenceEntry, SourceInfo
from siso_ref010.parsing import EntityTypeXmlParser


@pytest.mark.parametrize(
    "fields,key",
    [
        ((0, 0, 0, 0, 0, 0, 0), 0),
        ((1, 1, 0, 0, 0, 0, 0), 0x0101000000000000),
        ((0, 0, 1, 0, 0, 0, 0), 4294967296),
        ((1, 2, 225, 7, 8, 7, 1), 72621510476957441),
        ((255, 255, 65535, 255, 255, 255, 255), -1),
    ],
)
def test_wire_fixtures(fields, key):
    entity = EntityType(*fields)
    assert entity.to_key() == key
    assert EntityType.from_key(key) == entity
    assert EntityType.from_string(str(entity)) == entity
    assert EntityType.from_bytes(entity.to_bytes()) == entity
    assert len(entity.to_bytes()) == 8
    assert entity.to_key(signed=False) == key & ((1 << 64) - 1)
    assert (
        create_key(
            kind=KindCode(fields[0]),
            domain=DomainCode(fields[1]),
            country=CountryCode(fields[2]),
            category=CategoryCode(fields[3]),
            subcategory=SubcategoryCode(fields[4]),
            specific=SpecificCode(fields[5]),
            extra=ExtraCode(fields[6]),
        )
        == key
    )


def test_wire_bytes_match_independent_dis_entity_type_vector():
    # OpenDIS serializes uint8, uint8, uint16, then four uint8s:
    # https://github.com/open-dis/open-dis-python/blob/master/opendis/dis7.py
    # M1A2 code values come from the independent tutorial example:
    # https://github.com/open-dis/dis-tutorial/blob/master/EntityStatePDUs.md
    entity = EntityType.from_string("1.1.225.1.1.3.0")
    assert entity.to_bytes() == bytes.fromhex("01 01 00 e1 01 01 03 00")
    assert entity.to_key(signed=False) == 0x010100E101010300


def test_seeded_full_width_roundtrips():
    randomizer = random.Random(0x5150)
    for _ in range(10000):
        key = randomizer.getrandbits(64)
        entity = EntityType.from_key(key)
        assert entity.to_key(signed=False) == key
        assert entity.to_bytes() == key.to_bytes(8, "big")
        assert EntityType.from_string(str(entity)) == entity
        assert EntityType.from_key(entity.to_key()) == entity


@pytest.mark.parametrize(
    "text",
    [
        "",
        "1.2.3",
        "1.2.3.4.5.6.7.8",
        "1..3.4.5.6.7",
        "-1.2.3.4.5.6.7",
        "1.2.3.4.5.6.NaN",
        "1.2.3.4.5.6.1e1",
        "1.2.3.4.5.6.0x10",
        "256.2.3.4.5.6.7",
        "1.2.65536.4.5.6.7",
    ],
)
def test_invalid_strings(text):
    with pytest.raises(ValueError):
        EntityType.from_string(text)


@pytest.mark.parametrize("key", [-(1 << 63) - 1, 1 << 64])
def test_key_bounds(key):
    with pytest.raises(ValueError):
        EntityType.from_key(key)


@pytest.mark.parametrize("value", [True, 1.1, "1", None])
def test_reject_coercion(value):
    with pytest.raises(TypeError):
        EntityType(value, 0, 0, 0, 0, 0, 0)
    with pytest.raises(TypeError):
        EntityType.from_key(value)
    with pytest.raises(TypeError):
        create_key(
            kind=KindCode(value),
            domain=DomainCode(0),
            country=CountryCode(0),
            category=CategoryCode(0),
            subcategory=SubcategoryCode(0),
            specific=SpecificCode(0),
            extra=ExtraCode(0),
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("kind", -1),
        ("kind", 256),
        ("domain", 256),
        ("country", -1),
        ("country", 65536),
        ("category", 256),
        ("subcategory", 256),
        ("specific", 256),
        ("extra", 256),
    ],
)
def test_create_key_rejects_out_of_range_fields(field, value):
    values = {
        "kind": KindCode(1),
        "domain": DomainCode(2),
        "country": CountryCode(225),
        "category": CategoryCode(1),
        "subcategory": SubcategoryCode(1),
        "specific": SpecificCode(3),
        "extra": ExtraCode(0),
    }
    values[field] = value
    with pytest.raises(SisoRef010ValueError) as error:
        create_key(**values)
    assert error.value.code == "field_out_of_range"
    assert error.value.context["field"] == field


def test_native_methods():
    entity = EntityType.from_string("1|2|3|4|5|6|7", "|")
    assert entity.to_string() == "1.2.3.4.5.6.7"
    assert EntityType.from_key(entity.to_key()) == entity
    assert entity.get_kind() is EntityKind.PLATFORM
    assert entity.get_domain() is EntityDomain.AIR
    with pytest.raises(ValueError):
        EntityType.from_string("123", "")
    with pytest.raises(ValueError):
        EntityType.from_bytes(b"\x00")


@pytest.mark.parametrize("value", [5.562, -1, 11, float("nan"), float("inf"), True])
def test_invalid_kind(value):
    assert create_entity_kind_from_number(value) is None


@pytest.mark.parametrize("value", [3.562, -1, 6, 10, float("nan"), float("inf"), True])
def test_invalid_domain(value):
    assert create_entity_domain_from_number(value) is None


@pytest.mark.parametrize(
    "name,kind",
    [
        ("Other", EntityKind.OTHER),
        ("PLATFORM", EntityKind.PLATFORM),
        ("life form", EntityKind.LIFE_FORM),
        ("sensor/EMITTER", EntityKind.SENSOR_EMITTER),
        ("Lava", None),
    ],
)
def test_kind_names(name, kind):
    assert create_entity_kind_from_string(name) == kind


def test_domain_names():
    assert create_entity_domain_from_string("LAND") is EntityDomain.LAND
    assert create_entity_domain_from_string("space") is EntityDomain.SPACE
    assert create_entity_domain_from_string(" Land") is None  # Leading whitespace is not ignored.
    assert create_entity_kind_from_number(9) is EntityKind.SENSOR_EMITTER
    assert create_entity_domain_from_number(4) is EntityDomain.SUBSURFACE


@pytest.mark.parametrize(
    "entry, message",
    [
        ({"value": 1, "value_min": 1, "value_max": 2}, "both a scalar value and a range"),
        ({"value": None, "value_min": 3, "value_max": 2}, "minimum exceeds maximum"),
        ({"value": None, "value_min": None, "value_max": None}, "requires a value or value range"),
    ],
)
def test_reference_entries_enforce_scalar_and_range_shapes(entry, message):
    with pytest.raises(ValueError, match=message):
        ReferenceEntry(
            tag="enumrow",
            value=entry["value"],
            value_min=entry["value_min"],
            value_max=entry["value_max"],
            description="fixture",
            source=SourceInfo(attributes=()),
        )


def test_standard_reference_lookups_support_names_and_unique_uids():
    standard = EntityTypeXmlParser.from_string(
        '<ebv><enum uid="7" name="Example"><enumrow value="1"/></enum>'
        '<enum uid="8" name="Example"><enumrow value="2"/></enum></ebv>'
    )

    assert standard.enumeration("Example") is None
    assert tuple(table.uid for table in standard.enumerations_named("Example")) == (7, 8)
    assert standard.enumeration_by_uid(8).name == "Example"
    assert standard.enumeration("Missing") is None
    assert standard.enumeration_by_uid(9) is None
