# Source and data

The package bundles SISO-REF-010 XML editions v20 through v37 in a solid XZ
archive and the v2.7 XSD. The runtime decompresses only the selected edition
into memory when a bundled catalog is requested; v37 is the default.

`data/standards/PROVENANCE.json` is the single registry for edition sources,
the bundled schema, recovery archive members, and source verification. All
XML editions matched their recorded upstream bytes by SHA-256 and Git blob
SHA-1. The XSD matched the copy extracted from the supplied SISO v37 publisher
archive.

The runtime decompresses the requested XML in memory and parses it directly.
The parser returns a structured Python model; the lookup catalog is derived
from its Entity Types hierarchy and enumeration tables. JSON is available for
API/CLI results, not as a parallel catalog source.

The recovery materials record the source attribution `Reprinted with permission
from SISO Inc.` See the [source and redistribution notice](../src/dis_entity_types/data/standards/LICENSE_NOTICE.md).
