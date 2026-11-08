# Source and data

The package bundles SISO-REF-010 XML editions v20 through v37 in a solid XZ
archive and the v2.7 XSD. The runtime decompresses only the selected edition
into memory when a bundled catalog is requested; v37 is the default. Historical
XSDs for v20–v29 are kept under `tools/standards-xsds/` for maintainer checks
and are excluded from the runtime wheel.

`data/standards/PROVENANCE.json` is the single registry for edition sources,
the bundled schema, recovery archive members, and recorded source byte checks.
Its entries say that each XML matched the recorded source by SHA-256 and Git
blob SHA-1 when the registry was prepared. The XSD matched the copy extracted
from the supplied SISO v37 publisher archive. These records establish byte
identity with the cited locations, not publisher authentication.

Run `python -m tools.check_standards_provenance` to fetch the registry's
recorded HTTPS sources and verify their XML payloads against both SHA-256 and
Git blob SHA-1. The check is separate from the offline bundled checksum check.
It verifies byte identity with those recorded locations; it does not establish
a publisher signature. In the 2026-11-08 evaluation run, v20–v36 matched and
the SISO v37 archive endpoint returned HTTP 403, so that run could not verify
v37. The result is a point-in-time network check; rerun the command to refresh
it.

The runtime decompresses the requested XML in memory and parses it directly.
The parser returns a structured Python model; the lookup catalog is derived
from its Entity Types hierarchy and enumeration tables. JSON is available for
API/CLI results, not as a parallel catalog source.

The recovery materials record the source attribution `Reprinted with permission
from SISO Inc.` See the [source and redistribution notice](../src/siso_ref010/data/standards/LICENSE_NOTICE.md).
The library code is separately licensed under Apache-2.0; see the repository
[`LICENSE`](../LICENSE). This code license does not establish redistribution
rights for SISO source files or schemas.
