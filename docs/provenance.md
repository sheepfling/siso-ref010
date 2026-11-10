# Edition sources

The package includes the verified editions listed in the bundled index. The
original XML files are tracked in the repository and packed into an XZ stream
for installed builds. The runtime reads the selected edition from that pack.

`src/siso_ref010/data/standards/PROVENANCE.json` is the single source registry.
It records edition sources, schema validation sources, and checksums. Historical
schema namespaces come from the corresponding edition entry, avoiding a second
editable copy of that metadata.

Each XML retains its source copyright and terms. Read that XML for the exact
text; this page does not restate it.

## Verify source bytes

The network check compares available source bytes with the registry:

```sh
python -m tools.siso_ref010.check_standards_provenance
```

It limits each download to 50 MiB and ZIP XML members to 50 MiB both per member
and in aggregate before accepting their hashes.

Offline XSD validation is separate:

```sh
python -m tools.siso_ref010.check_standards_xsd
```
