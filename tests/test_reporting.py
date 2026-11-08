from siso_ref010.reporting import _edition_label


def test_edition_label_prefers_explicit_number_and_recognizes_title_suffix():
    assert _edition_label("SISO-REF-010-v37", 36) == "Edition 36"
    assert _edition_label("SISO-REF-010-v37") == "Edition 37"
    assert _edition_label("Custom source") == "Custom source"
