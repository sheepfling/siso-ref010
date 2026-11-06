"""Native picker behavior is testable without Tk or a display."""

import pytest

from siso_entity_type import EntityTypeAPI, SisoEnum
from siso_entity_type.picker import Field, PickerState


@pytest.fixture(scope="module")
def api():
    return EntityTypeAPI()


@pytest.fixture
def state(api):
    return PickerState(api)


@pytest.mark.parametrize(
    "value",
    ["", "1.2", "1.2.3.4.5.6.7.8", "-1.0.0.0.0.0.0", "256.0.0.0.0.0.0", "1.0.65536.0.0.0.0", "x.0.0.0.0.0.0"],
)
def test_load_is_atomic(state, value):
    state.load("1.3.153.6.4.2.0")
    before = state.entity
    with pytest.raises(ValueError):
        state.load(value)
    assert state.entity == before


def test_repeat_load_preserves_every_field(state):
    for _ in range(3):
        state.load("255.254.65535.253.252.251.250")
        assert state.entity == SisoEnum(255, 254, 65535, 253, 252, 251, 250)
        for field in Field:
            assert getattr(state.entity, field) in [item.value for item in state.choices(field)]


@pytest.mark.parametrize(
    "field,value,expected",
    [
        (Field.COUNTRY, 225, (1, 3, 225, 0, 0, 0, 0)),
        (Field.KIND, 2, (2, 0, 153, 0, 0, 0, 0)),
        (Field.DOMAIN, 2, (1, 2, 153, 0, 0, 0, 0)),
        (Field.CATEGORY, 7, (1, 3, 153, 7, 0, 0, 0)),
        (Field.SUBCATEGORY, 5, (1, 3, 153, 6, 5, 0, 0)),
        (Field.SPECIFIC, 3, (1, 3, 153, 6, 4, 3, 0)),
        (Field.EXTRA, 2, (1, 3, 153, 6, 4, 2, 2)),
    ],
)
def test_cascades_reset_all_descendants(state, field, value, expected):
    state.load("1.3.153.6.4.2.1")
    state.select(field, value)
    assert state.entity.as_tuple() == expected


@pytest.mark.parametrize("field", list(Field))
def test_reselect_is_idempotent_and_clear_is_explicit(state, field):
    state.load("1.3.153.6.4.2.1")
    before = state.entity
    state.select(field, getattr(before, field))
    assert state.entity == before
    state.select(field, None)
    assert getattr(state.entity, field) == 0
    state.select(field, None)
    assert getattr(state.entity, field) == 0


def test_clearing_zero_still_resets_descendants(state):
    state.load("1.3.153.6.4.0.1")
    state.select(Field.SPECIFIC, None)
    assert state.entity.extra == 0


@pytest.mark.parametrize(
    "field,value",
    [(Field.KIND, 256), (Field.COUNTRY, 65536), (Field.EXTRA, -1), (Field.DOMAIN, True), (Field.KIND, 1.0)],
)
def test_invalid_selections_are_atomic(state, field, value):
    state.load("1.3.153.6.4.2.1")
    before = state.entity
    with pytest.raises((TypeError, ValueError)):
        state.select(field, value)
    assert state.entity == before


def test_catalog_options_follow_parents(state, api):
    state.load("1.3.153.6.4.2.0")
    assert set(api.choices("categories", 1, 3, 153).items) <= set(state.choices("category"))
    assert set(api.choices("specifics", 1, 3, 153, 6, 4).items) <= set(state.choices("specific"))
    state.select("country", 225)
    assert set(api.choices("categories", 1, 3, 225).items) <= set(state.choices("category"))


def test_search_count_selection_and_reset(state):
    results = state.search("f803")
    assert results.total == len(results.hits) == 1
    assert results.hits[0].description == "F803 Tromp"
    state.select_result(0)
    assert str(state.entity) == "1.3.153.6.4.2.0"
    state.select_result(0)
    assert str(state.entity) == "1.3.153.6.4.2.0"
    for query in ("", "f8", "no-matching-description-xyz"):
        assert state.search(query).total == 0
        with pytest.raises(IndexError):
            state.select_result(0)
    with pytest.raises(IndexError):
        state.select_result(-1)
    state.reset()
    assert str(state.entity) == "0.0.0.0.0.0.0"
    assert state.results.total == 0
