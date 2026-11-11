# Changelog

## Unreleased

- Stream completed XML tables and entity branches to reduce cold-start memory while preserving the full source model, validation, ordering, and exact XML retrieval.
- Share immutable change-request annotations within a parse, and add reproducible cold-start benchmarks with all-edition model-parity checks.
- Use absolute repository links in the package description while retaining local README links in the checkout.

## 0.1.0a0

- Add entity and enumeration value histories and pairwise edition diffs with JSON/text CLI output, filters, and UUID-based move/recode recognition.
- Retain enumeration table description/header annotations for inspection and comparison.
- Derive the package version from Git tags with setuptools-scm; expose the source edition on each selected API instance.
- Use Pydantic v2 for bounded entity fields, validated source records, and automatic model serialization.
- Use Pydantic `model_dump()` directly for API and CLI JSON output, including nested seven-field entity values.
- Use named keyword arguments for low-level `create_key()` calls and expose the info result as `CatalogInfo`.
- Build immutable `CatalogData` through a functional projection, leaving `EntityTypeCatalog` as a lookup facade.
- Use nominal integer code types and an `EntityTypePrefix` model to keep field domains distinct in APIs and lookup maps.
- Parse SISO-REF-010 into a structured source model that retains all enum tables, entity hierarchy, ranges, metadata, change requests, and cross-references.
- Build entity lookup choices from the Entity Types hierarchy, resolving subcategory enumeration references instead of mixing unrelated category tables into the catalog.
- Remove flattened JSON catalog import/export and the CLI parse-to-JSON command; alternate data sources are loaded directly from XML.
- Add the v37 C2 Logical Object entity kind to the source-aligned kind model.
- Use official SISO-REF-010-v37 XML and XSD as packaged source data.
- Load the bundled lookup catalog directly from the XML.
- Remove the embedded catalog snapshot, copied JavaScript source, and comparison harness.
- Add typed Python exceptions and validate the packaged XML against its XSD in CI.
