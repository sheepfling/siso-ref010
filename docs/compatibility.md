# Scope and compatibility

## What is ported

- `packages/lib`: entity kind/domain enumerations, descriptions and conversions;
  seven-field `SisoEnum`; exact 64-bit keys; lookup collections; fallback and
  fully qualified descriptions; case-insensitive search; constants; a compatibility
  `Utils.createKey` and generic `LongKeyMap` using Python integer keys.
- `packages/parser`: entity-type XML extraction, factory methods, counts, exact-key
  getters, and upstream-format JSON output. The XML snapshot and generated JSON
  match the pinned Git blobs. Generated TypeScript schema machinery is replaced
  by an explicit namespace-aware Python XML traversal, not a full XSD validator.
- Principal picker workflow: terminal hierarchy selection, CLI search and lookup.

## What is not ported

The Vue/Vuetify GUI, responsive styling, browser clipboard, client-side store,
web hosting, npm publication/build pipeline and generated TypeScript types are not
Python features in this delivery. The terminal picker is a replacement workflow,
not pixel or UI-state parity with the Vue application. `initializeSpecific` and
`initializeExtra` are upstream parser implementation hooks, not exposed as Python
incremental mutation methods. Parse a complete XML document instead.

The full repository scope was inspected (three packages), not assumed to consist
only of the main library. A source snapshot used by the reference generator is
included under `vendor/upstream`. There has been no public repository creation,
push, deployment, or package publication.

## Preserved behavior worth knowing

- Keys retain all 64 bits, with fields kind/domain/country/category/subcategory/
  specific/extra at shifts 56/48/32/24/16/8/0. `to_key()` and `create_key()` return
  signed integers like the upstream `long.js` construction. `signed=False`
  returns the same bits as an unsigned integer. JSON keys stay decimal strings.
- `get_all_domains()` returns composite `(kind << 8) | domain` keys, rather than
  conflating kind-specific domain labels. Prefer `get_all_domains_of(kind)`.
- Country 0 records participate in category/subcategory/specific/extra collections.
  Where a numeric child code collides, **the last source-map entry wins**. This is
  insertion-order behavior, not an unconditional country-specific override.
- Short descriptions try full and generic-country keys, then less-specific
  parents, in the exact upstream order. Missing descriptions return `"-"`.
- Qualified descriptions include `Unknown category/subcategory/specific/extra N`
  labels and remove only adjacent duplicate descriptions, as upstream does.
- Search visits subcategory/specific/extra descriptions only, not category-only,
  country or kind labels. It uses lowercase substring matching, not fuzzy search.
- `DEFAULT_DEPRECATED` is unused in upstream. Deprecated rows are not filtered.
- Applicability parsing mirrors upstream's comma/range rules, not a general
  grammar for all possible future standard expressions.
- Snake-case enum conversions return `IntEnum` members. The source-style
  `createEntityKindFromNumber`, `createEntityDomainFromNumber`, `getKind`, and
  `getDomain` return **names**, matching the actual upstream runtime and tests
  (its TypeScript signatures misleadingly say enum values). Both uppercase Python
  enum members and original spellings such as `EntityKind.Platform` are available.

## Intentional Python differences

- `SisoEnum` is an immutable dataclass. It rejects booleans, floats, malformed
  strings, negative fields and out-of-range values instead of coercing them into
  NaN, zero or truncated values. Seven unsigned decimal components are required;
  surrounding component whitespace is allowed. Low-level `create_key` masks
  integer fields as upstream does, but does not coerce nonintegers.
- Signed and unsigned 64-bit inputs are accepted by `from_key`; values outside
  that range are rejected. No approximate float keys are accepted.
- Initialization is synchronous and replaces all data, clearing indexes/caches.
  Upstream's reinitialization merges maps and can retain stale qualified text.
  Returned Python dictionaries are copies.
- Parser filenames are normal filesystem paths. Upstream concatenates them onto
  its installed module directory. Singleton enum rows are supported rather than
  ignored by upstream's array-only enum-row guard.
- Invalid required XML values/descriptions fail clearly; DTD/entity declarations
  are rejected. This tightens malformed-input behavior, which was not specified
  as stable by upstream. Parser field packing still masks integer values like
  upstream; the parser is not a full wire-range or schema validator.
- `to_string()` on the parser emits valid XML using ElementTree; prefixes,
  declaration, comments, CDATA and whitespace are not byte-preserved. Upstream's
  XMLBuilder output is not treated as a canonical source serialization.
- Python `None` replaces JavaScript `undefined`. Map objects are dictionaries
  (or the optional `LongKeyMap` compatibility wrapper); keys are Python integers.
  `LongKeyMap.for_each` does not support structural mutation during iteration.
- `SisoEnumType` is a compatibility alias to the concrete Python dataclass, not
  the original TypeScript interface. No async API or browser fetch is required.

Parity is established for the pinned dataset and the measured reference cases,
not every possible malformed document, unknown future SISO schema, or every
observable JavaScript coercion and map-iteration edge case.
