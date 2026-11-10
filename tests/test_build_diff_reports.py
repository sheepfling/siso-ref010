import pytest

from tools.siso_ref010.build_diff_reports import _parse_pair


def test_report_pair_argument_is_not_tied_to_specific_editions() -> None:
    assert _parse_pair("20:37") == (20, 37)


def test_report_pair_argument_rejects_ambiguous_values() -> None:
    for value in ("35", "35:36:37", "x:37"):
        with pytest.raises(ValueError):
            _parse_pair(value)
