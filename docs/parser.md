# Native Python parser APIs

The XML parser uses Python's standard library. It extracts the same entity-type
lookup tables as the upstream parser; it does not validate the complete SISO XSD.
The bundled full XML-to-catalog fixture test checks exact values and insertion
order. SISO data attribution and the upstream source notices still apply.

## Incremental lookup rows

```python
from siso_entity_type.parser import SisoEnumsParser
from siso_entity_type.xml_types import SpecificElement, ExtraElement

parser = SisoEnumsParser.from_string("<ebv/>")
parser.initialize_specific(
    1,
    2,
    225,
    7,
    8,
    SpecificElement(9, "Aircraft variant", ExtraElement(1, "Equipment variant")),
    "Parent description",
)
```

`initialize_specific` / `initializeSpecific` takes one `SpecificElement` or a
sequence, plus kind, domain, country, category, subcategory and parent text.
`initialize_extra` / `initializeExtra` additionally takes the specific number
and one `ExtraElement` or a sequence. Specific records accept a single extra or
a tuple of extras. Both methods return `None`. Duplicate keys replace earlier
text. Lookup methods, counts, `to_data`, and written catalogs see these changes.
As upstream does, these methods modify lookup tables, not the source document:
`to_string` still serializes the original XML.

These typed dataclasses are Python-facing records, not XML attribute dictionaries.
Values must be integers in 0..255 (country 0..65535), excluding booleans, and
descriptions must be strings. Invalid batches raise `ParseError` without partial
updates. Unlike upstream's coercion/skipping, invalid values are rejected.
Qualified descriptions use the parser's `qualified` and `delimiter` settings.

## XML-as-JSON conversion

`xml_types.Convert.to_siso_xml_types(text)` and
`Convert.siso_xml_types_to_json(document)` validate and round-trip the separate
XML-as-JSON interchange document exported by the upstream parser package.
Aliases are `toSISOXMLTypes` and `sISOXMLTypesToJson`. This is **not** the compact
`siso-enums.json` catalog format and does not parse XML or populate a parser.
`SISOXMLTypes` is a typed dictionary alias over recursive `JSONValue` values;
validation returns ordinary dictionaries/lists. `XMLShapeError` reports malformed
JSON, missing fields, unexpected fields, invalid enums, and structural errors.

The document requires `?xml`, `?xml-stylesheet`, and `ebv` sections. Validation
covers metadata, revisions, dictionaries, enums, entity/object hierarchies,
bitfields, records, and jammer descriptions. Optional fields may be omitted,
not set to null. XML attribute values remain strings. Runtime string enums
`Status`, `Type`, and `Key` retain upstream member spellings.

This is a newly authored Python validator informed by the upstream declarations,
not a mechanical translation of its generated validation engine or a claim of
clean-room implementation. The generated TypeScript interfaces and runtime
unions disagree in several places. Python deliberately normalizes singleton and
array child shapes to the declared interfaces rather than reproducing generated
`Purple`/`Fluffy` union inconsistencies. For example a singleton entity accepts
the same category shapes as an array entry, and datatype records have a required
name and optional constrained type. Enum-row ranges accept optional change
references and footnotes in either singleton or array form. Consequently this
converter is not a byte-for-byte or rejection-for-rejection clone of that engine.

Dates are validated ISO 8601 strings and remain strings, rather than becoming
JavaScript Date objects. Permissive JavaScript date parsing and numeric date
coercion are not reproduced. Pretty-printed JSON retains Unicode characters.
The validator checks structure, not semantic UID references or DIS field ranges;
use the XML parser and entity model for entity-type interpretation. Generated
compile-time-only interface names are not duplicated as Python runtime classes.
