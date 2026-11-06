import random

import pytest

from siso_entity_type import (
    EntityDomain,
    EntityKind,
    SisoEnum,
    Utils,
    create_entity_domain_from_number,
    create_entity_domain_from_string,
    create_entity_kind_from_number,
    create_entity_kind_from_string,
    create_key,
    createEntityDomainFromNumber,
    createEntityKindFromNumber,
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
    entity = SisoEnum(*fields)
    assert entity.to_key() == key
    assert SisoEnum.from_key(key) == entity
    assert SisoEnum.from_string(str(entity)) == entity
    assert SisoEnum.from_bytes(entity.to_bytes()) == entity
    assert len(entity.to_bytes()) == 8
    assert entity.to_key(signed=False) == key & ((1 << 64) - 1)
    assert Utils.createKey(*fields) == key


def test_seeded_full_width_roundtrips():
    randomizer = random.Random(0x5150)
    for _ in range(10000):
        key = randomizer.getrandbits(64)
        entity = SisoEnum.from_key(key)
        assert entity.to_key(signed=False) == key
        assert entity.to_bytes() == key.to_bytes(8, "big")
        assert SisoEnum.from_string(str(entity)) == entity
        assert SisoEnum.from_key(entity.to_key()) == entity


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
        SisoEnum.from_string(text)


@pytest.mark.parametrize("key", [-(1 << 63) - 1, 1 << 64])
def test_key_bounds(key):
    with pytest.raises(ValueError):
        SisoEnum.from_key(key)


@pytest.mark.parametrize("value", [True, 1.1, "1", None])
def test_reject_coercion(value):
    with pytest.raises(TypeError):
        SisoEnum(value, 0, 0, 0, 0, 0, 0)
    with pytest.raises(TypeError):
        SisoEnum.from_key(value)
    with pytest.raises(TypeError):
        create_key(value, 0, 0, 0, 0, 0, 0)


def test_low_level_masking_and_aliases():
    assert create_key(257, -1, 65536, 256, 0, 0, 0) == create_key(1, 255, 0, 0, 0, 0, 0)
    entity = SisoEnum.fromString("1|2|3|4|5|6|7", "|")
    assert entity.toString() == "1.2.3.4.5.6.7"
    assert SisoEnum.fromKey(entity.toKey()) == entity
    assert entity.get_kind() is EntityKind.PLATFORM
    assert entity.getKind() == "Platform"
    assert entity.get_domain() is EntityDomain.AIR
    assert entity.getDomain() == "Air"
    with pytest.raises(ValueError):
        SisoEnum.from_string("123", "")
    with pytest.raises(ValueError):
        SisoEnum.from_bytes(b"\x00")


@pytest.mark.parametrize("value", [5.562, -1, 10, float("nan"), float("inf"), True])
def test_invalid_kind(value):
    assert create_entity_kind_from_number(value) is None
    assert createEntityKindFromNumber(value) is None


@pytest.mark.parametrize("value", [3.562, -1, 6, 10, float("nan"), float("inf"), True])
def test_invalid_domain(value):
    assert create_entity_domain_from_number(value) is None
    assert createEntityDomainFromNumber(value) is None


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
    assert create_entity_domain_from_string(" Land") is None  # Upstream does not trim names.
    assert createEntityKindFromNumber(9) == "SensorEmitter"
    assert createEntityDomainFromNumber(4) == "Subsurface"


def test_map_compatibility():
    from siso_entity_type import LongKeyMap

    table = LongKeyMap[str]()
    table.set(1, "a")
    table.set(2, "b")
    table.set(1, "c")
    assert table.size == 2
    assert table.keys() == [1, 2]
    assert table.values() == ["c", "b"]
    assert table.entries() == [(1, "c"), (2, "b")]
    assert table.get(1) == "c"
    assert table.has(1)
    assert table.get(0) is None
    seen = []
    table.forEach(lambda value, key, owner: seen.append((value, key, owner is table)))
    assert seen == [("c", 1, True), ("b", 2, True)]
    assert table.delete(1)
    assert not table.delete(1)
    table.clear()
    assert table.size == 0
    assert EntityKind.Platform is EntityKind.PLATFORM
    assert EntityDomain.Air is EntityDomain.AIR


def test_description_helpers():
    from siso_entity_type import get_entity_domain_description, get_entity_kind_description

    assert get_entity_kind_description(9) == "Sensor/Emitter"
    assert get_entity_kind_description(255) is None
    assert get_entity_domain_description(1) == "Land"
    assert get_entity_domain_description(255) is None


@pytest.mark.parametrize("value", [0.5, float("inf"), float("-inf"), float("nan")])
def test_nonintegral_enum_inputs_return_none(value):
    from siso_entity_type import create_entity_domain_from_number, create_entity_kind_from_number

    assert create_entity_kind_from_number(value) is None
    assert create_entity_domain_from_number(value) is None
