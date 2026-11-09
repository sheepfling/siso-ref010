"""Checks for the small public-API consumer example."""

import pytest

from examples.entity_type_consumer import main


def test_default_example_reports_edition_resolution_and_bytes(capsys):
    assert main([]) == 0
    output = capsys.readouterr().out
    assert "Edition: SISO-REF-010-v37" in output
    assert "Resolution: Exact match (exact)" in output
    assert "Entity Type bytes:" in output
    assert "not a complete PDU" in output


def test_unknown_code_keeps_unresolved_field_visible(capsys):
    assert main(["--entity-type", "1.2.225.1.3.255.0"]) == 0
    output = capsys.readouterr().out
    assert "Unknown supplied component (unknown)" in output
    assert "Unresolved fields: specific" in output


def test_invalid_code_is_reported_as_command_error(capsys):
    with pytest.raises(SystemExit) as error:
        main(["--entity-type", "1.2.225"])
    assert error.value.code == 2
    assert "Expected seven unsigned decimal fields" in capsys.readouterr().err
