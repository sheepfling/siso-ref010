# Provenance and licensing

## Source lock

- Repository: https://github.com/TNO-MST/siso-entity-type
- Revision: `bb195c647b6f9c4b7bea4e5a10e6c560a0b0bceb`
- Upstream lib/parser versions: `1.0.3`
- Python port version: `0.2.0` (independent version; not a published distribution)
- XML title/date: `SISO-REF-010-v35`, `2025-04-27`
- JSON Git blob: `674b445bff0feab409c8bee1b24873dc33a4716c`
- XML Git blob: `0ad0a1af71adfb03ac0049802d6376f1cbd7c9ed`

The original JSON (1,100,916 bytes) is packaged as runtime data. The original XML
(6,083,213 bytes) is a test fixture in source distributions, not included in the
wheel. Both are tested against their Git blob hashes. The vendored TypeScript
source files were checked against the recursive Git tree stored with the source
snapshot. The two large fixtures were retrieved by Git blob SHA after GitHub's
contents endpoint returned an empty content field for them; no content was
reconstructed or inferred from excerpts.

## Two different sets of terms

TNO's original source is under Apache-2.0, with its copyright line retained in
`LICENSE` and `NOTICE`. The Python code is a modified derivative under that license.

The XML has an additional SISO copyright notice. That notice is copied verbatim
into `SISO-DATA-NOTICE.txt` and retained in the XML fixture. It grants a general,
royalty-free license to copy, distribute, display and make derivative works of
Schema and API for all purposes with the required attribution. Its separate
Documentation paragraph allows those uses only for noncommercial purposes unless
express written permission is obtained from the SISO Inc. Board of Directors.

**Reprinted with permission from SISO Inc.**

The notice does not precisely classify every extracted descriptive string. This
port preserves the upstream dataset and notice, but does not offer a legal
conclusion that every downstream commercial use or redistribution is cleared.
In particular, the software's Apache-2.0 metadata is not a license replacement for
the standard's documentation. Confirm applicable rights for a commercial product
that redistributes descriptive material. No SISO or TNO endorsement is implied.
