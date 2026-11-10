"""Typed validation models for checked-in edition manifests and pack indexes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class SourceReference(StrictModel):
    type: Literal["git-commit", "publisher-release", "svn-revision", "svn-tag"]
    value: StrictStr = Field(min_length=1)


class SourceVerification(StrictModel):
    sha256_match: Literal[True]
    git_blob_sha1_match: Literal[True]


class SourceRecord(StrictModel):
    provider: Literal["GitHub", "SISO", "SourceForge"]
    repository: StrictStr = Field(min_length=1)
    reference: SourceReference
    path: StrictStr = Field(min_length=1)
    url: StrictStr = Field(pattern=r"^https://")
    verification: SourceVerification


class SourceHistory(StrictModel):
    status: Literal["resolved"]
    recorded_at: StrictStr = Field(min_length=1)
    attempted_urls: list[StrictStr]
    finding: StrictStr = Field(min_length=1)
    resolution: StrictStr = Field(min_length=1)


class ProvenanceEntry(StrictModel):
    status: Literal["verified"]
    version: StrictInt = Field(ge=1)
    file: StrictStr = Field(min_length=1)
    bytes: StrictInt = Field(ge=0)
    sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    git_blob_sha1: StrictStr = Field(pattern=r"^[0-9a-f]{40}$")
    title: StrictStr = Field(min_length=1)
    edition_date: StrictStr = Field(min_length=1)
    release: StrictStr
    schema_namespace: StrictStr = Field(min_length=1)
    elements: StrictInt = Field(ge=0)
    enum_tables: StrictInt = Field(ge=0)
    primary_source: SourceRecord
    verified_mirrors: list[SourceRecord]
    source_history: list[SourceHistory]
    bundle_file: StrictStr = Field(min_length=1)


class ProvenanceArtifact(StrictModel):
    kind: Literal["xml-schema"]
    file: StrictStr = Field(min_length=1)
    bytes: StrictInt = Field(ge=0)
    sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    git_blob_sha1: StrictStr = Field(pattern=r"^[0-9a-f]{40}$")
    schema_namespace: StrictStr = Field(min_length=1)
    primary_source: SourceRecord


class SourceVerificationSummary(StrictModel):
    checked_at_utc: StrictStr = Field(min_length=1)
    method: StrictStr = Field(min_length=1)
    versions: list[StrictInt]


class ValidationSchema(StrictModel):
    version: StrictInt = Field(ge=1)
    path: StrictStr = Field(min_length=1)
    sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    source_url: StrictStr = Field(pattern=r"^https://")
    source_reference: StrictStr = Field(min_length=1)


class ProvenanceRegistry(StrictModel):
    verification_scope: StrictStr = Field(min_length=1)
    registry_schema: StrictInt = Field(ge=2, le=2)
    entries: list[ProvenanceEntry]
    source_verification: SourceVerificationSummary
    artifacts: list[ProvenanceArtifact]
    validation_schemas: list[ValidationSchema]

    @model_validator(mode="after")
    def edition_versions_are_unique(self) -> ProvenanceRegistry:
        versions = [entry.version for entry in self.entries]
        if len(versions) != len(set(versions)):
            raise ValueError("Provenance edition versions must be unique")
        return self


class PackedEdition(StrictModel):
    version: StrictInt = Field(ge=1)
    date: StrictStr = Field(min_length=1)
    sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    size: StrictInt = Field(ge=0)
    offset: StrictInt = Field(ge=0)
    title: StrictStr = Field(min_length=1)
    source_file: StrictStr = Field(min_length=1)


class StandardPackIndex(StrictModel):
    format: Literal["siso-ref010-snapshot-pack-1"]
    latest_version: StrictInt = Field(ge=1)
    verified_scope: StrictStr = Field(min_length=1)
    raw_size: StrictInt = Field(ge=0)
    pack_size: StrictInt = Field(ge=0)
    pack_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    editions: list[PackedEdition]

    @model_validator(mode="after")
    def edition_layout_is_consistent(self) -> StandardPackIndex:
        if not self.editions:
            raise ValueError("Pack index must contain at least one edition")
        if self.latest_version != self.editions[0].version:
            raise ValueError("Pack index latest_version must identify its first edition")
        if len({edition.version for edition in self.editions}) != len(self.editions):
            raise ValueError("Pack index edition versions must be unique")
        return self
