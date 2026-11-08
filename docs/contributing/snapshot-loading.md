# Snapshot loading measurements

Run `python -m tools.benchmark_snapshot_loading --iterations 3` to compare cold
snapshot retrieval with complete `EntityTypeAPI.bundled(version)` construction.
Each measurement runs in a fresh process; Python startup and module imports are
outside the timed region. Snapshot retrieval includes loading the index,
checking the compressed archive fingerprint, seeking the edition in the XZ
stream, and verifying the edition SHA-256. API construction includes that
retrieval, XML parsing, and catalog projection.

## Local observation

Environment: Python 3.14.10, macOS 26.6.2, arm64; three fresh-process samples
per operation on 2026-11-08.

| Edition | Snapshot retrieval median (range) | API construction median (range) |
| --- | ---: | ---: |
| v37 | 68.42 ms (68.27–68.44) | 690.21 ms (683.44–692.88) |
| v30 | 134.20 ms (134.19–134.42) | 1,141.78 ms (1,137.74–1,145.20) |
| v20 | 199.03 ms (198.67–199.31) | 954.63 ms (953.15–963.27) |

These measurements describe one machine and one run. They are not performance
guarantees or a cross-platform comparison. The increase in older-edition
retrieval is consistent with the archive's solid XZ layout: each edition has a
logical uncompressed offset, but no independent compressed frame. Seeking to an
older edition can decompress earlier stream contents before returning its XML.

When comparing future layouts, use the same versions and fresh-process method,
record Python and OS versions, and compare both raw retrieval and complete API
construction. Any alternative should preserve byte-for-byte edition recovery
and per-edition checksum checks.
