import json
import runpy
import sys

import pytest
from pydantic import ValidationError

from dis_entity_types import (
    EntityType,
    EntityTypeAPI,
    EntityTypeCatalog,
    EntityTypePrefix,
    EntityTypeTypeError,
    EntityTypeValueError,
    EntityTypeXmlParser,
)
from dis_entity_types.cli import _error_type, main
from dis_entity_types.model import (
    create_entity_domain_from_number,
    create_entity_kind_from_number,
    get_entity_domain_description,
    get_entity_kind_description,
)
from dis_entity_types.projection import (
    _applicability_values,
    _child_code,
    _entry_values,
    _field_values,
    _referenced_table,
    _walk_entry,
)
from dis_entity_types.reference import ChangeRequest, ReferenceEntry, SourceInfo, _unsigned_integer


def test_pydantic_and_integer_boundary_edges():
    assert create_entity_kind_from_number(1.0) is not None
    assert create_entity_domain_from_number(2.0) is not None
    assert get_entity_kind_description(255) is None
    assert get_entity_domain_description(255) is None

    with pytest.raises(TypeError, match="at most 7"):
        EntityType(*range(8))
    with pytest.raises(TypeError, match="multiple values"):
        EntityType(1, kind=1)
    with pytest.raises(ValidationError):
        EntityType(kind=1)
    with pytest.raises(ValueError, match="contiguous"):
        EntityTypePrefix(kind=1, country=1)
    with pytest.raises(EntityTypeValueError) as error:
        EntityTypePrefix.from_values(tuple(range(8)))
    assert error.value.code == "invalid_prefix_length"


def test_reference_model_validation_edges():
    assert _unsigned_integer(4) == 4
    assert _unsigned_integer(" 7 ") == 7
    for invalid in (True, "-1", 1.5):
        with pytest.raises(ValueError):
            _unsigned_integer(invalid)
    with pytest.raises(ValidationError):
        ChangeRequest(minimum=2, maximum=1)

    source = SourceInfo(attributes=(("name", "sample"),))
    assert source.get("name") == "sample"
    assert source.get("missing") is None
    with pytest.raises(ValidationError):
        ReferenceEntry(
            tag="specific",
            value=None,
            value_min=2,
            value_max=None,
            description="bad range",
            source=SourceInfo(attributes=()),
        )


def test_projection_parser_edges():
    assert _field_values("X,,2-3") == (0, 2, 3)
    assert _applicability_values(None, 0) == ()
    assert _applicability_values("1", 0) == (1,)
    assert _applicability_values("1", 1) == ()
    with pytest.raises(EntityTypeValueError):
        _field_values("other")
    with pytest.raises(EntityTypeValueError):
        _field_values("3-1")
    with pytest.raises(ValueError):
        _child_code(2, 1)
    with pytest.raises(EntityTypeValueError) as error:
        _referenced_table("bad", {})
    assert error.value.code == "unresolved_enumeration_reference"

    empty = ReferenceEntry(
        tag="specific",
        value=None,
        value_min=None,
        value_max=None,
        description=None,
        source=SourceInfo(attributes=()),
    )
    assert _entry_values(empty) == ()
    assert tuple(_walk_entry(empty, (), {})) == ()

    no_domain_labels = EntityTypeXmlParser.from_string(
        '<ebv><enum uid="8" name="Platform Domain" applicability="1"><enumrow value="2"/></enum></ebv>'
    )
    assert not EntityTypeCatalog(no_domain_labels).data.domains


def test_public_catalog_and_cli_error_edges(tmp_path, monkeypatch, capsys):
    catalog = EntityTypeCatalog.bundled()
    assert catalog.data is catalog.data
    assert all(isinstance(key, tuple) for key in catalog.get_all_domains())

    api = EntityTypeAPI()
    with pytest.raises(EntityTypeTypeError):
        api.choices("countries", object())  # type: ignore[arg-type]
    assert _error_type(TypeError()) == "TypeError"
    assert _error_type(ValueError()) == "ValueError"
    assert _error_type(IndexError()) == "IndexError"
    assert _error_type(RuntimeError()) == "RuntimeError"

    missing = tmp_path / "missing.xml"
    with pytest.raises(SystemExit) as exit_code:
        main(["--xml", str(missing), "info"])
    assert exit_code.value.code == 2
    capsys.readouterr()

    import dis_entity_types.cli as cli

    def interrupt(_value):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "encode_entity", interrupt)
    assert main(["key", "1.2.3.4.5.6.7"]) == 130
    assert "Interrupted" in capsys.readouterr().err
    assert main(["--json", "key", "1.2.3.4.5.6.7"]) == 130
    assert json.loads(capsys.readouterr().err)["error"]["type"] == "Interrupted"


def test_module_entry_point(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["dis-entity-types", "--version"])
    with pytest.raises(SystemExit) as exit_code:
        runpy.run_module("dis_entity_types", run_name="__main__")
    assert exit_code.value.code == 0
