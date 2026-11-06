# Package name and publication plan

Status: private review candidate. No PyPI or TestPyPI upload, GitHub release,
release tag, publisher authorization, API token, or publishing workflow is part
of this review. The current CI only validates and builds locally on its runners.

## Proposed name

Use **dis-entity-types** for the repository and Python distribution. DIS means
Distributed Interactive Simulation. The name describes the entity-type model,
lookup catalog, parser, and CLI without presenting the package as an official
SISO or TNO product. This is a naming recommendation, not trademark clearance.

The Python import remains `siso_entity_type`, preserving the existing local
bundle's API. Distribution names need not match import names. The new
`dis-entity-types` command and existing `siso-entity-type` command are equivalent.
A future import rename is a separate compatibility decision for review.

Checks on November 6, 2026:

| Candidate | Official PyPI JSON endpoint | Exact public GitHub name found |
| --- | --- | --- |
| dis-entity-types | HTTP 404 | No |
| dis-entity-catalog | HTTP 404 | No |
| dis-entity-type | HTTP 404 | No (two substring matches) |

Sources: [dis-entity-types](https://pypi.org/pypi/dis-entity-types/json),
[dis-entity-catalog](https://pypi.org/pypi/dis-entity-catalog/json), and
[dis-entity-type](https://pypi.org/pypi/dis-entity-type/json).
GitHub searches used each candidate with `in:name`. GitHub names are
owner-scoped; public search cannot establish whether a private name exists.
A 404 is not a reservation or acceptance guarantee. PyPI normalizes hyphens,
underscores, and periods, and can reject reserved or prohibited names. Check
again immediately before the first authorized release.

## Release gate: software and data have different terms

The Python port is an Apache-2.0 derivative of the pinned TNO source. Retain the
original license, attribution, NOTICE, and modification notices. No endorsement
or affiliation is claimed. See [provenance.md](provenance.md).

The review wheel bundles the original SISO JSON. The source archive also includes
the full XML and an oracle fixture containing descriptions. SISO's notice grants
all-purpose Schema/API reuse with attribution but limits Documentation reuse to
noncommercial purposes unless written permission is obtained. The source does
not precisely classify every extracted description. Existing attribution alone
does not settle that question.

**Do not upload this review artifact to a public index or make this repository
public until the owner resolves the data rights decision.** Private review is
not a legal conclusion about downstream redistribution rights.

Choose one before public release:

1. Confirm with the relevant rights holder or qualified adviser that the intended
   dataset distribution and commercial downstream use are allowed, retaining
   written evidence and exact applicable terms; or
2. Prepare a code-only package with user-supplied XML/JSON, synthetic test data,
   and no copied standard descriptions in runtime data, fixtures, oracle outputs,
   vendored examples, source archives, or documentation. Audit both wheel and
   sdist. Do not substitute an automatic download to avoid this review.

The current mixed artifact uses `Apache-2.0 AND LicenseRef-SISO-Data` metadata.
`LicenseRef-SISO-Data` names the separate `SISO-DATA-NOTICE.txt`, not a newly granted
license. This is deliberately not described as uniformly Apache-licensed.

## Recommended publishing route

Use GitHub Actions with PyPI Trusted Publishing, rather than a stored long-lived
PyPI API token. Authorize the exact owner/repository/workflow/environment tuple.
Keep build/test jobs separate from the upload job; only that job should receive
`id-token: write`. Require a human release decision, review exact artifacts,
and use protected release environments where the account plan supports them.
Do not grant OIDC upload permissions to pull-request jobs.

Proposed values after the owner approves the final name and repository:

- Project: `dis-entity-types`.
- Owner: `sheepfling`; repository: `dis-entity-types` (private review repository created).
- Workflow: `release.yml`, added in a later reviewed change.
- Separate environments: `testpypi` and `pypi`.
- Separate pending publishers in the respective index accounts.

PyPI can create a project on the pending publisher's first successful upload.
Pending publishers do not reserve project names. TestPyPI is a separate service
and an upload there is public distribution too, so the same data-rights gate
applies. No publisher has been registered by preparing this plan.

Creating a publisher establishes ongoing authority. The owner must explicitly
approve that exact access before it is configured. This review only documents it.

Official references:

- [PyPI: create a project with a Trusted Publisher](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
- [PyPI: publisher configuration and environments](https://docs.pypi.org/trusted-publishers/adding-a-publisher/)
- [PyPI: publish with a Trusted Publisher](https://docs.pypi.org/trusted-publishers/using-a-publisher/)
- [Python Packaging guide: GitHub Actions publishing](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/)
- [Python Packaging guide: TestPyPI](https://packaging.python.org/en/latest/guides/using-testpypi/)

## Release checklist

- [ ] Approve the final distribution/repository name and import namespace policy.
- [ ] Resolve and record data rights, or complete a code-only distribution audit.
- [ ] Decide the first public version; `0.2.0` currently denotes a local review build.
- [x] Add verified repository and issue URLs to project metadata; documentation
      is included in the repository.
- [ ] Pass CI for the exact reviewed commit, including Python 3.11–3.14 and
      Windows/macOS smoke tests. Do not count configured jobs as executed checks.
- [ ] Build wheel and sdist from a clean checkout; validate metadata with Twine,
      inspect their files and notices, and install each through a fresh consumer
      environment. Re-run the suite from the sdist.
- [ ] Approve and configure the exact Trusted Publisher grants and any protected
      environments. Pin publishing actions to reviewed immutable commits.
- [ ] Approve the public TestPyPI release; install from TestPyPI using `--no-deps`
      (there are no runtime dependencies) and repeat consumer checks.
- [ ] Review the production version, artifact hashes, and release notes; approve
      the PyPI upload separately. Do not overwrite or reuse a published version.
- [ ] Verify the resulting PyPI metadata and a clean install before announcing it.
