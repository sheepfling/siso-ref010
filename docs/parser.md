# XML parser

`EntityTypeXmlParser` reads SISO-REF-010 XML with Python's standard library and
returns an immutable Pydantic `EntityTypeStandard`. Pydantic validates numeric
fields, value ranges, and nested records during construction. It does not turn
the source into a
JSON catalog or flatten the entity hierarchy during parsing.

```python
from siso_ref010 import ReferenceCatalog, EntityTypeXmlParser

standard = EntityTypeXmlParser.from_file("SISO-REF-010.xml")
print(standard.title, standard.date)

entity_kinds = standard.enumeration("Entity Kind")
print(entity_kinds.uid, entity_kinds.applicability)
print(entity_kinds.entries[0].description)

catalog = ReferenceCatalog(standard)  # Optional lookup projection
```

`from_file()` accepts a string or any `os.PathLike[str]` value. File paths are
normalized to `Path` inside the package.

Use `EntityTypeXmlParser.from_string(xml)` for in-memory parsing. Namespaced and
unnamespaced `<ebv>` documents are accepted. DTD and entity declarations are
rejected.

## Structured source model

- `EntityTypeStandard` contains root attributes, namespace, revision records,
  copyright text, every `<enum>` table, and the Entity Types CET. Its `date`
  field is a `datetime.date | None`; the source attributes retain the original
  string.
- `EnumerationTable` retains its UID, name, applicability, declared size,
  source attributes, `<enumrow>` or `<enumrow_range>` entries, and table-level
  description/header annotations.
- `EntityBranch` and `ReferenceEntry` preserve categories through extras,
  including ranges and nested children.
- `SourceInfo` keeps element attributes, `<meta>` key/value pairs, and direct
  change request values or ranges. Enumeration cross-references remain attached
  to their source entries and can be followed through `EntityTypeStandard`.

`standard.enumerations_named(name)` and
`standard.enumeration_tables_by_uid(uid)` return all matching definitions. An
empty tuple/list means missing, one item means unique, and multiple items are
ambiguous. The singular `enumeration(name)` and `enumeration_by_uid(uid)`
helpers return a table only when the match is unique. `ReferenceCatalog` and
`EditionInspector` expand cross-references from all matching definitions,
preserving duplicate rows so lookup can report ambiguous entity codes instead
of silently selecting one table.

This is a structured model of standard data, not a lossless XML infoset. Unknown
extension elements, comments, processing instructions, and formatting are not
retained. The parser checks basic structure and numeric values but does not
validate arbitrary files against the complete XSD. The bundled XML is validated
against the packaged XSD in CI. Use `standard.model_dump(mode="json")` to
serialize the structured model.
