"""Report high-confidence repository hygiene regressions without rewriting files.

Run from the repository root with ``python -m tools.repo_hygiene.check_repository_hygiene``.
Use ``--format json`` for a machine-readable report.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError, model_validator

BASELINE = Path(__file__).with_name("repository-hygiene-baseline.json")
Severity = Literal["error", "review"]


@dataclass(frozen=True, slots=True, order=True)
class FindingFingerprint:
    rule_id: str
    path: str
    evidence: str


class BaselineAcknowledgement(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    rule_id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    reason: str = Field(min_length=1)

    @property
    def fingerprint(self) -> FindingFingerprint:
        return FindingFingerprint(self.rule_id, self.path, self.evidence)

    @model_validator(mode="after")
    def fields_are_not_whitespace(self) -> BaselineAcknowledgement:
        fields = (
            ("rule_id", self.rule_id),
            ("path", self.path),
            ("evidence", self.evidence),
            ("reason", self.reason),
        )
        for field_name, value in fields:
            if not value.strip():
                raise ValueError(f"Baseline field {field_name!r} must not be blank")
        return self


class RepositoryHygieneBaseline(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    schema_version: StrictInt = Field(ge=1, le=1)
    acknowledged: list[BaselineAcknowledgement]

    @model_validator(mode="after")
    def fingerprints_are_unique(self) -> RepositoryHygieneBaseline:
        fingerprints = [record.fingerprint for record in self.acknowledged]
        if len(fingerprints) != len(set(fingerprints)):
            raise ValueError("Baseline acknowledgement fingerprints must be unique")
        return self


@dataclass(frozen=True, slots=True)
class Finding:
    rule_id: str
    category: str
    severity: Severity
    path: str
    line: int
    evidence: str
    reason: str

    @property
    def fingerprint(self) -> FindingFingerprint:
        return FindingFingerprint(self.rule_id, self.path, self.evidence)


def _finding(
    rule_id: str,
    category: str,
    severity: Severity,
    path: str,
    line: int,
    evidence: str,
    reason: str,
) -> Finding:
    return Finding(rule_id, category, severity, path, line, evidence.strip(), reason)


def _assignment_names(node: ast.Assign | ast.AnnAssign) -> set[str]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return {target.id for root in targets for target in ast.walk(root) if isinstance(target, ast.Name)}


def _call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else None
    return None


def _integer(node: ast.expr | None) -> int | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
        return node.value
    return None


def _source_findings(path: str, source: str) -> tuple[Finding, ...]:
    """Detect the reviewed edition-coupling patterns with AST context."""
    tree = ast.parse(source, filename=path)
    lines = source.splitlines()
    findings: list[Finding] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            names = _assignment_names(node)
            value = node.value
            if (
                names & {"DEFAULT_VERSION", "PACKAGE_REVISION"}
                and value is not None
                and _integer(value) is not None
            ):
                name = sorted(names & {"DEFAULT_VERSION", "PACKAGE_REVISION"})[0]
                line = lines[node.lineno - 1]
                findings.append(
                    _finding(
                        "repo.edition.literal_default",
                        "historical_coupling",
                        "error",
                        path,
                        node.lineno,
                        line,
                        (
                            f"{name} should come from the edition registry or be removed "
                            "when it is study metadata."
                        ),
                    )
                )

        called_name = _call_name(node.func) if isinstance(node, ast.Call) else None
        if (
            isinstance(node, ast.Call)
            and called_name is not None
            and called_name.endswith(".add_argument")
            and node.args
        ):
            flag = node.args[0].value if isinstance(node.args[0], ast.Constant) else None
            default = next((keyword.value for keyword in node.keywords if keyword.arg == "default"), None)
            is_version_argument = flag == "--standard-version" or (
                flag == "--version" and path.startswith("tools/siso_ref010/benchmark_")
            )
            fixed_version_list = (
                flag == "--versions"
                and path.startswith("tools/siso_ref010/")
                and isinstance(default, (ast.Tuple, ast.List))
                and bool(default.elts)
                and all(_integer(item) is not None for item in default.elts)
            )
            if (is_version_argument and _integer(default) is not None) or fixed_version_list:
                findings.append(
                    _finding(
                        "repo.edition.cli_default",
                        "historical_coupling",
                        "error",
                        path,
                        node.lineno,
                        lines[node.lineno - 1],
                        "General tools should derive edition defaults from bundled index metadata.",
                    )
                )

        if isinstance(node, ast.Compare) and path == "tools/siso_ref010/check_installed.py":
            left = node.left
            if isinstance(left, ast.Call) and _call_name(left.func) == "len" and left.args:
                target = left.args[0]
                is_versions = (isinstance(target, ast.Name) and "version" in target.id.casefold()) or (
                    isinstance(target, ast.Attribute) and "version" in target.attr.casefold()
                )
                fixed_count = any(_integer(value) is not None for value in node.comparators)
                if is_versions and fixed_count:
                    findings.append(
                        _finding(
                            "repo.edition.fixed_count",
                            "historical_coupling",
                            "error",
                            path,
                            node.lineno,
                            lines[node.lineno - 1],
                            "Installed-package behavior should not require an exact edition count.",
                        )
                    )

        if isinstance(node, ast.Call) and path == "tools/siso_ref010/check_standards_xsd.py":
            if _call_name(node.func) == "range" and len(node.args) == 2:
                if all(_integer(value) is not None for value in node.args):
                    findings.append(
                        _finding(
                            "repo.xsd.fixed_coverage_range",
                            "historical_coupling",
                            "error",
                            path,
                            node.lineno,
                            lines[node.lineno - 1],
                            "Historical XSD coverage should derive from recorded edition namespaces.",
                        )
                    )

        if isinstance(node, ast.Call) and _call_name(node.func) == "_python_module" and path == "tools/ci.py":
            if (
                node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "tools.siso_ref010.check_standards_xsd"
            ):
                try:
                    versions_index = next(
                        index
                        for index, argument in enumerate(node.args)
                        if isinstance(argument, ast.Constant) and argument.value == "--versions"
                    )
                except StopIteration:
                    continue
                if any(
                    isinstance(argument, ast.Constant)
                    and isinstance(argument.value, str)
                    and argument.value.isdecimal()
                    for argument in node.args[versions_index + 1 :]
                ):
                    findings.append(
                        _finding(
                            "repo.ci.fixed_edition_endpoints",
                            "historical_coupling",
                            "error",
                            path,
                            node.lineno,
                            lines[node.lineno - 1],
                            "Hosted edition endpoints should come from the bundled edition index.",
                        )
                    )

        if (
            isinstance(node, ast.Call)
            and _call_name(node.func) == "SisoRef010API.bundled"
            and path.startswith("examples/")
        ):
            if node.args and _integer(node.args[0]) is not None:
                findings.append(
                    _finding(
                        "repo.example.pinned_edition",
                        "historical_coupling",
                        "review",
                        path,
                        node.lineno,
                        lines[node.lineno - 1],
                        (
                            "Pin an edition in an example only when it demonstrates reproducibility "
                            "or explicit selection."
                        ),
                    )
                )

    return tuple(findings)


def _artifact_reason(path: str) -> str | None:
    name = Path(path).name
    if name == ".DS_Store" or name.startswith("._") or "__MACOSX" in Path(path).parts:
        return "macOS archive metadata should not be tracked."
    if path.endswith((".zip", ".whl", ".tar.gz", ".xz", ".pyc", ".coverage")):
        return "Generated archives and local runtime artifacts belong outside tracked source."
    return None


def _tracked_paths() -> tuple[str, ...]:
    result = subprocess.run(["git", "ls-files", "-z"], check=True, capture_output=True)
    return tuple(path for item in result.stdout.split(b"\0") if (path := item.decode("utf-8")))


def scan_repository() -> tuple[Finding, ...]:
    tracked = _tracked_paths()
    findings: list[Finding] = []
    for path in tracked:
        if not Path(path).is_file():
            continue
        artifact_reason = _artifact_reason(path)
        if artifact_reason:
            findings.append(
                _finding(
                    "repo.artifact.generated",
                    "ephemeral_artifact",
                    "error",
                    path,
                    1,
                    path,
                    artifact_reason,
                )
            )
        if Path(path).name == "SOURCES.json" and (
            path.startswith("src/siso_ref010/data/standards/")
            or path.startswith("tools/siso_ref010/standards-xsds/")
        ):
            findings.append(
                _finding(
                    "repo.provenance.duplicate_registry",
                    "duplicate_authority",
                    "error",
                    path,
                    1,
                    path,
                    "Edition and schema source facts belong in the single PROVENANCE.json registry.",
                )
            )
        if path.startswith(("tools/", "examples/")) and path.endswith(".py"):
            findings.extend(_source_findings(path, Path(path).read_text(encoding="utf-8")))
        if path.endswith(".md"):
            source = Path(path).read_text(encoding="utf-8").splitlines()
            for number, line in enumerate(source, start=1):
                if "private review candidate" in line.casefold():
                    findings.append(
                        _finding(
                            "repo.docs.stale_review_status",
                            "stale_documentation",
                            "error",
                            path,
                            number,
                            line,
                            "Remove obsolete private-review status from durable user documentation.",
                        )
                    )

    ignored_result = subprocess.run(
        ["git", "ls-files", "-ci", "--exclude-standard", "-z"],
        check=True,
        capture_output=True,
    )
    for item in ignored_result.stdout.split(b"\0"):
        path = item.decode("utf-8")
        if path and Path(path).is_file():
            findings.append(
                _finding(
                    "repo.artifact.tracked_ignored",
                    "ephemeral_artifact",
                    "error",
                    path,
                    1,
                    path,
                    "This tracked file matches a Git ignore rule; review whether it is generated data.",
                )
            )
    return tuple(sorted(findings, key=lambda finding: (finding.path, finding.line, finding.rule_id)))


def _load_baseline() -> RepositoryHygieneBaseline:
    raw = json.loads(BASELINE.read_text(encoding="utf-8"))
    try:
        baseline = RepositoryHygieneBaseline.model_validate(raw)
    except ValidationError as error:
        raise ValueError(f"Invalid repository hygiene baseline {BASELINE}: {error}") from error
    return baseline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    try:
        findings = scan_repository()
        baseline = _load_baseline()
    except (
        OSError,
        subprocess.CalledProcessError,
        UnicodeDecodeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        print(f"Repository hygiene scan failed: {error}", file=sys.stderr)
        return 2

    findings_by_fingerprint = {finding.fingerprint: finding for finding in findings}
    baseline_by_fingerprint = {record.fingerprint: record for record in baseline.acknowledged}
    acknowledged = tuple(sorted(set(findings_by_fingerprint) & set(baseline_by_fingerprint)))
    stale = tuple(sorted(set(baseline_by_fingerprint) - set(findings_by_fingerprint)))
    new_errors = tuple(
        finding
        for finding in findings
        if finding.severity == "error" and finding.fingerprint not in baseline_by_fingerprint
    )
    if args.format == "json":
        print(
            json.dumps(
                {
                    "report_type": "repository_hygiene",
                    "schema_version": 1,
                    "findings": [asdict(finding) for finding in findings],
                    "acknowledged": [
                        {
                            "rule_id": key.rule_id,
                            "path": key.path,
                            "evidence": key.evidence,
                            "reason": baseline_by_fingerprint[key].reason,
                        }
                        for key in acknowledged
                    ],
                    "stale_acknowledgements": [[key.rule_id, key.path, key.evidence] for key in stale],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        if not findings:
            print("No repository hygiene findings.")
        for finding in findings:
            state = "ERROR" if finding.severity == "error" else "REVIEW"
            if finding.fingerprint in baseline_by_fingerprint:
                state = "ACKNOWLEDGED"
            print(f"{state} {finding.category} {finding.path}:{finding.line}: {finding.evidence}")
            print(f"  {finding.reason}")
        if stale:
            print(f"Stale baseline acknowledgements: {len(stale)}")

    return 1 if new_errors or stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
