# Edition sources

The package includes SISO-REF-010 editions v20–v37. The original XML files are
tracked in the repository and packed into an XZ stream for installed builds.
The runtime reads the selected edition from that pack.

`src/siso_ref010/data/standards/PROVENANCE.json` is the source registry. It
contains edition and XSD source references and recorded checksums.

Each XML retains its source copyright and terms. Read that XML for the exact
text; this page does not restate it.

## Verify source bytes

The network check compares available source bytes with the registry:

```sh
python -m tools.check_standards_provenance
```

Offline XSD validation is separate:

```sh
python -m tools.check_standards_xsd
```
