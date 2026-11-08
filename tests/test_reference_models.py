import pytest
from pydantic import ValidationError

from siso_ref010 import EntityTypeXmlParser
from siso_ref010.reference import ChangeRequest, ReferenceEntry, SourceInfo


def _entry(**updates):
    values = {
        "tag": "enumrow",
        "value": 1,
        "value_min": None,
        "value_max": None,
        "description": "one",
        "source": SourceInfo(attributes=()),
    }
    values.update(updates)
    return ReferenceEntry(**values)


def test_source_numeric_text_is_normalized_but_not_coerced_from_booleans():
    assert _entry(value=" 12 ").value == 12
    for invalid in (True, "-1", "1.0", None):
        with pytest.raises(ValidationError):
            _entry(value=invalid)


@pytest.mark.parametrize(
    "updates, message",
    [
        ({"value_min": 1}, "must supply both endpoints"),
        ({"value": 1, "value_min": 1, "value_max": 2}, "both a scalar value and a range"),
        ({"value": None, "value_min": 3, "value_max": 2}, "range minimum exceeds maximum"),
        ({"value": None, "value_min": None, "value_max": None}, "requires a value or value range"),
        ({"tag": "enumrow_range", "value": None}, "requires a value or value range"),
    ],
)
def test_reference_entry_enforces_scalar_and_range_shape(updates, message):
    with pytest.raises(ValidationError, match=message):
        _entry(**updates)


def test_change_request_rejects_reversed_unsigned_ranges():
    assert ChangeRequest(minimum="1", maximum=2).minimum == 1
    with pytest.raises(ValidationError, match="range minimum exceeds maximum"):
        ChangeRequest(minimum=3, maximum=2)


def test_standard_supports_exact_name_and_uid_table_lookup():
    standard = EntityTypeXmlParser.from_string(
        '<ebv><enum uid="7" name="Example"><enumrow value="1" description="one"/></enum></ebv>'
    )
    assert standard.enumeration("Example") is standard.enumerations[0]
    assert standard.enumeration("Missing") is None
    assert standard.enumerations_named("Example") == [standard.enumerations[0]]
    assert standard.enumerations_named("Missing") == []
    assert standard.enumeration_by_uid(7) is standard.enumerations[0]
    assert standard.enumeration_by_uid(8) is None
