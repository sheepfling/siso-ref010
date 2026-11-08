# Source data and provenance

The package includes SISO-REF-010 editions v20–v37. Original XML files are
tracked in the repository and packed into one XZ stream for installed builds.
The runtime decompresses the edition selected by the caller.

`src/siso_ref010/data/standards/PROVENANCE.json` is the source registry. It
records each edition's source location, byte count, SHA-256, Git blob hash, and
verification result. It also records the source for the packaged XSD. The
registry is the single place for edition source references.

Run the network check with:

```sh
python -m tools.check_standards_provenance
```

This checks source bytes against the registry. It does not verify a publisher
signature or establish redistribution permission. Offline XSD validation is
separate:

```sh
python -m tools.check_standards_xsd
```

The library code is under Apache-2.0. SISO source data has separate terms, and
public redistribution rights are unresolved. See the [data notice](../src/siso_ref010/data/standards/LICENSE_NOTICE.md)
before copying or bundling it.
