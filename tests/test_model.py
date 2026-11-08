import random

import pytest

from dis_entity_types import (
    CategoryCode,
    CountryCode,
    DomainCode,
    EntityDomain,
    EntityKind,
    EntityType,
    ExtraCode,
    KindCode,
    SpecificCode,
    SubcategoryCode,
)
from dis_entity_types.model import (
    create_entity_domain_from_number,
    create_entity_domain_from_string,
    create_entity_kind_from_number,
    create_entity_kind_from_string,
    create_key,
)


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


def test_low_level_masking_and_native_methods():
    assert create_key(
        kind=KindCode(257),
        domain=DomainCode(-1),
        country=CountryCode(65536),
        category=CategoryCode(256),
        subcategory=SubcategoryCode(0),
        specific=SpecificCode(0),
        extra=ExtraCode(0),
    ) == create_key(
        kind=KindCode(1),
        domain=DomainCode(255),
        country=CountryCode(0),
        category=CategoryCode(0),
        subcategory=SubcategoryCode(0),
        specific=SpecificCode(0),
        extra=ExtraCode(0),
    )
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
