import builtins
import hashlib
import json
import subprocess
from dataclasses import FrozenInstanceError, asdict, replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml
from typer.testing import CliRunner

from archguard.application.ports.architecture import (
    ArchitectureConstraintEvaluatorPort,
    ArchitectureProfileLoaderPort,
    ArchitectureProfileReaderPort,
    ArchitectureProfileWriterPort,
    ArchitectureReportReaderPort,
    ArchitectureReportWriterPort,
)
from archguard.application.services.architecture import (
    CompileArchitectureProfile,
    EvaluateArchitecture,
)
from archguard.application.services.constraint_engine import (
    DeterministicConstraintEvaluator,
    assign_components,
)
from archguard.application.services.graph_builder import DeterministicGraphBuilder
from archguard.application.services.repository import UnsafePathError
from archguard.domain.architecture_profile import (
    ArchitectureProfile,
    ForbidDependency,
    ModuleSelector,
)
from archguard.domain.architecture_report import CycleEvidence, DependencyEvidence
from archguard.domain.graph import GraphBuildOptions, RepositoryGraph
from archguard.domain.repository import AnalysisOptions
from archguard.entrypoints.cli.app import app
from archguard.infrastructure.architecture_profiles import (
    LocalArchitectureProfiles,
    canonical_profile,
    decode_profile,
    load_profile_yaml,
)
from archguard.infrastructure.architecture_reports import (
    LocalArchitectureReports,
    canonical_report,
    decode_report,
)
from archguard.infrastructure.graph_artifacts import LocalGraphArtifacts
from archguard.infrastructure.repository_analyzer import LocalRepositoryAnalyzer

pytestmark = pytest.mark.unit


def profile_data() -> dict[str, Any]:
    return {
        "architecture_profile_schema_version": "1",
        "id": "example",
        "name": "Example",
        "components": [
            {"id": "first", "selectors": [{"type": "module_exact", "value": "a"}]},
            {"id": "second", "selectors": [{"type": "module_exact", "value": "b"}]},
        ],
        "rules": [
            {
                "id": "no-dependency",
                "type": "forbid_dependency",
                "source": "first",
                "target": "second",
            }
        ],
    }


def profile(data: dict[str, Any] | None = None) -> ArchitectureProfile:
    return load_profile_yaml(
        yaml.safe_dump(
            json.loads(json.dumps(data if data is not None else profile_data()))
        ).encode()
    )


def graph(tmp_path: Path, files: dict[str, str], top_level: bool = False) -> RepositoryGraph:
    root = tmp_path / "source"
    root.mkdir(exist_ok=True)
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    snapshot = LocalRepositoryAnalyzer().analyze(root, AnalysisOptions())
    return DeterministicGraphBuilder().build(
        snapshot, GraphBuildOptions("top_level" if top_level else "full_module")
    )


def evaluate(g: RepositoryGraph, data: dict[str, Any] | None = None) -> Any:
    return DeterministicConstraintEvaluator().evaluate(g, profile(data))


@pytest.mark.parametrize(
    "mutation",
    [
        "schema",
        "duplicate-component",
        "duplicate-rule",
        "undefined",
        "selector",
        "rule",
        "field",
        "severity",
        "policy",
        "component-limit",
        "rule-limit",
        "selector-limit",
        "reference-limit",
        "unsafe",
        "rule-field",
        "nonstring",
        "scalar",
        "description",
        "empty-id",
        "invalid-id",
        "empty-name",
        "empty-components",
        "empty-selectors",
        "bool-control",
        "contradictory",
        "path-glob",
        "unknown-selector-field",
    ],
)
def test_profile_rejects(mutation: str) -> None:
    data = profile_data()
    rule = data["rules"][0]
    if mutation == "schema":
        data["architecture_profile_schema_version"] = "2"
    elif mutation == "duplicate-component":
        data["components"] *= 2
    elif mutation == "duplicate-rule":
        data["rules"] *= 2
    elif mutation == "undefined":
        rule["target"] = "missing"
    elif mutation == "selector":
        data["components"][0]["selectors"][0]["type"] = "regex"
    elif mutation == "rule":
        rule["type"] = "inference"
    elif mutation == "field":
        data["unknown"] = True
    elif mutation == "severity":
        rule["severity"] = "fatal"
    elif mutation == "policy":
        data["assignment"] = {"unassigned": "allow"}
    elif mutation == "component-limit":
        data["components"] *= 129
    elif mutation == "rule-limit":
        data["rules"] *= 2049
    elif mutation == "selector-limit":
        data["components"][0]["selectors"] *= 257
    elif mutation == "reference-limit":
        data["rules"] = [{"id": "cycle", "type": "forbid_cycles", "components": ["first"] * 257}]
    elif mutation == "unsafe":
        data["components"][0]["selectors"] = [{"type": "path_exact", "value": "../a.py"}]
    elif mutation == "rule-field":
        rule["unknown"] = True
    elif mutation == "nonstring":
        data[1] = "bad"  # type: ignore[index]
    elif mutation == "scalar":
        data["architecture_profile_schema_version"] = 1
    elif mutation == "description":
        data["description"] = 123
    elif mutation == "empty-id":
        data["id"] = ""
    elif mutation == "invalid-id":
        rule["id"] = "Bad ID"
    elif mutation == "empty-name":
        data["name"] = ""
    elif mutation == "empty-components":
        data["components"] = []
    elif mutation == "empty-selectors":
        data["components"][0]["selectors"] = []
    elif mutation == "bool-control":
        rule["enabled"] = "true"
    elif mutation == "contradictory":
        rule["allowed"] = ["first"]
    elif mutation == "path-glob":
        data["components"][0]["selectors"] = [{"type": "path_prefix", "value": "src/*"}]
    elif mutation == "unknown-selector-field":
        data["components"][0]["selectors"][0]["bad"] = 1
    with pytest.raises(ValueError):
        profile(data)


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"[",
        b"null",
        b"[]",
        b"!!python/object:builtins.object {}",
        b"id: one\nid: two",
        b"a: &x [1]\nb: *x",
        b"1: value",
        b"a: {b: 1, b: 2}",
        b"a: !!unknown value",
        b"x" * (1024 * 1024 + 1),
        b"[" * 30 + b"0" + b"]" * 30,
    ],
)
def test_bad_yaml(raw: bytes) -> None:
    with pytest.raises(ValueError):
        load_profile_yaml(raw)


@pytest.mark.parametrize(
    "kind,value,module,path,expected",
    [
        ("module_exact", "demo.api", "demo.api", "src/api.py", True),
        ("module_exact", "demo.api", "demo.api.users", "src/api.py", False),
        ("module_prefix", "demo.api", "demo.api.users", "a.py", True),
        ("module_prefix", "demo.api", "demo.api", "a.py", True),
        ("module_prefix", "demo.api", "demo.apiv2", "a.py", False),
        ("path_exact", "src/api.py", "a", "src/api.py", True),
        ("path_exact", "src/api.py", "a", "src/api.py/x", False),
        ("path_prefix", "src/api", "a", "src/api/users.py", True),
        ("path_prefix", "src/api", "a", "src/api", True),
        ("path_prefix", "src/api", "a", "src/apiv2/a.py", False),
    ],
)
def test_selectors(kind: Any, value: str, module: str, path: str, expected: bool) -> None:
    assert ModuleSelector(kind, value).matches(module, path) is expected


def test_canonical_profile_order_and_immutability() -> None:
    first = profile()
    data = profile_data()
    data["components"].reverse()
    data["components"][0]["selectors"] *= 2
    assert profile(data) == first
    data["rules"].append(
        {"id": "disabled", "type": "forbid_cycles", "components": ["first"], "enabled": False}
    )
    before = profile(data)
    data["rules"].reverse()
    assert profile(data) == before
    assert decode_profile(canonical_profile(before)) == before
    assert before.profile_fingerprint != first.profile_fingerprint
    assert (
        load_profile_yaml(yaml.safe_dump(json.loads(json.dumps(data)), sort_keys=False).encode())
        == before
    )
    with pytest.raises(FrozenInstanceError):
        first.name = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        first.components[0].id = "changed"  # type: ignore[misc]
    with pytest.raises(ValueError):
        replace(first, profile_fingerprint="0" * 64)
    with pytest.raises(ValueError):
        ModuleSelector("path_exact", "/tmp/private")
    with pytest.raises(ValueError):
        ForbidDependency(id="bad", source="first", target="second", severity="error")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "action,severity,passed",
    [
        ("ignore", None, True),
        ("warn", "warning", True),
        ("error", "error", False),
    ],
)
def test_assignment_policies(
    tmp_path: Path, action: str, severity: str | None, passed: bool
) -> None:
    g = graph(tmp_path, {"a.py": "import b\nimport os\n", "b.py": "pass\n", "c.py": "pass\n"})
    data = profile_data()
    data["rules"] = []
    data["assignment"] = {"unassigned": action, "ambiguous": action}
    data["components"].append(
        {"id": "overlap", "selectors": [{"type": "path_exact", "value": "a.py"}]}
    )
    report = evaluate(g, data)
    assert report.summary.passed is passed
    assert report.summary.partial
    assert report.summary.internal_module_count == 3
    assert report.summary.assigned_module_count == 1
    assert report.summary.ambiguous_module_count == report.summary.unassigned_module_count == 1
    assert all(a.module_id.startswith("module:") for a in report.assignments)
    assert [d.severity for d in report.assignment_diagnostics] == (
        [] if severity is None else [severity] * 2
    )
    assert report.assignments[0].component_ids == ("first", "overlap")
    data["components"].reverse()
    assert evaluate(g, data) == report
    assert decode_report(canonical_report(report)) == report


def test_invalid_module_omission(tmp_path: Path) -> None:
    g = graph(tmp_path, {"bad-name.py": "import os\n", "a.py": "pass\n"})
    report = evaluate(g)
    assert tuple(a.module_id for a in report.assignments) == ("module:a",)
    assert report.summary.partial


@pytest.mark.parametrize("severity,passed", [("error", False), ("warning", True), ("info", True)])
def test_dependency_aggregation(tmp_path: Path, severity: str, passed: bool) -> None:
    g = graph(tmp_path, {"a.py": "import b\nimport b\n", "b.py": "pass\n"})
    data = profile_data()
    data["rules"][0]["severity"] = severity
    report = evaluate(g, data)
    assert report.summary.passed is passed
    assert report.summary.total_violation_count == 1
    assert not report.summary.partial
    evidence = report.violations[0].evidence
    assert isinstance(evidence, DependencyEvidence)
    assert evidence.occurrence_count == 2
    assert sorted(location.line for location in evidence.locations) == [1, 2]
    assert decode_report(canonical_report(report)) == report
    data["rules"][0]["enabled"] = False
    disabled = evaluate(g, data)
    assert not disabled.violations and disabled.summary.disabled_rules == 1
    assert disabled.summary.evaluated_rules == 0
    assert disabled.summary.passed


@pytest.mark.parametrize("include,expected", [(True, 1), (False, 0)])
def test_type_checking_dependency(tmp_path: Path, include: bool, expected: int) -> None:
    g = graph(
        tmp_path,
        {
            "a.py": "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import b\n",
            "b.py": "pass\n",
        },
    )
    data = profile_data()
    data["rules"][0]["include_type_checking"] = include
    assert len(evaluate(g, data).violations) == expected


@pytest.mark.parametrize("allowed,expected", [(["second"], 0), (["first"], 1), ([], 1)])
def test_allow_only(tmp_path: Path, allowed: list[str], expected: int) -> None:
    g = graph(tmp_path, {"a.py": "import b\nimport b\n", "b.py": "pass\n"})
    data = profile_data()
    data["rules"] = [
        {"id": "only", "type": "allow_only_dependencies", "source": "first", "allowed": allowed}
    ]
    report = evaluate(g, data)
    assert len(report.violations) == expected
    if expected:
        assert report.violations[0].evidence.occurrence_count == 2
    assert decode_report(canonical_report(report)) == report


@pytest.mark.parametrize(
    "rule_type", ["forbid_dependency", "allow_only_dependencies", "forbid_cycles"]
)
@pytest.mark.parametrize("ambiguous", [False, True])
def test_incomplete_assignments_skip(tmp_path: Path, rule_type: str, ambiguous: bool) -> None:
    g = graph(tmp_path, {"a.py": "import b\n", "b.py": "pass\n"})
    data = profile_data()
    if ambiguous:
        data["components"].append(
            {"id": "overlap", "selectors": [{"type": "module_exact", "value": "b"}]}
        )
    else:
        data["components"][1]["selectors"][0]["value"] = "c"
    if rule_type == "allow_only_dependencies":
        data["rules"] = [{"id": "only", "type": rule_type, "source": "first", "allowed": []}]
    elif rule_type == "forbid_cycles":
        data["rules"] = [{"id": "cycles", "type": rule_type, "components": ["first"]}]
    report = evaluate(g, data)
    assert report.summary.partial and report.summary.skipped_rules == 1
    assert not report.violations
    assert report.rule_results[0].reason == "incomplete_assignments"


@pytest.mark.parametrize(
    "rule_type,target,expected",
    [
        ("forbid_dependency", "second", 0),
        ("forbid_dependency", "first", 1),
        ("allow_only_dependencies", "first", 0),
        ("allow_only_dependencies", "second", 1),
    ],
)
def test_self_component(tmp_path: Path, rule_type: str, target: str, expected: int) -> None:
    g = graph(tmp_path, {"a.py": "import a\n"})
    data = profile_data()
    data["rules"] = [
        {
            "id": "self",
            "type": rule_type,
            "source": "first",
            **({"target": target} if rule_type == "forbid_dependency" else {"allowed": [target]}),
        }
    ]
    assert len(evaluate(g, data).violations) == expected


@pytest.mark.parametrize(
    "kind,value,expected",
    [
        ("external_exact", "fastapi.routing", 1),
        ("external_exact", "fastapi", 0),
        ("external_prefix", "fastapi", 1),
        ("external_prefix", "flask", 0),
        ("external_prefix", "fastapi_utils", 1),
        ("external_prefix", "fast", 0),
    ],
)
def test_external(tmp_path: Path, kind: str, value: str, expected: int) -> None:
    g = graph(
        tmp_path, {"a.py": "import fastapi.routing\nimport fastapi.routing\nimport fastapi_utils\n"}
    )
    data = profile_data()
    data["rules"] = [
        {
            "id": "external",
            "type": "forbid_external_dependency",
            "source": "first",
            "external": [{"type": kind, "value": value}],
        }
    ]
    report = evaluate(g, data)
    assert len(report.violations) == expected
    assert decode_report(canonical_report(report)) == report
    if expected:
        evidence = report.violations[0].evidence
        assert evidence.occurrence_count == (1 if value == "fastapi_utils" else 2)


def test_external_policy_and_type_checking(tmp_path: Path) -> None:
    files = {
        "a.py": "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import fastapi.routing\n"
    }
    g = graph(tmp_path, files)
    data = profile_data()
    data["rules"] = [
        {
            "id": "external",
            "type": "forbid_external_dependency",
            "source": "first",
            "external": [{"type": "external_prefix", "value": "fastapi"}],
        }
    ]
    assert len(evaluate(g, data).violations) == 1
    data["rules"][0]["include_type_checking"] = False
    assert not evaluate(g, data).violations
    collapsed = evaluate(graph(tmp_path, files, True), data)
    assert collapsed.summary.partial and collapsed.summary.skipped_rules == 1
    assert collapsed.rule_results[0].reason == "external_names_collapsed"
    assert decode_report(canonical_report(collapsed)) == collapsed


@pytest.mark.parametrize(
    "files,scope,include,count,tc",
    [
        ({"a.py": "import b\n", "b.py": "pass\n"}, ["first", "second"], True, 0, False),
        ({"a.py": "import b\n", "b.py": "import a\n"}, ["first", "second"], True, 1, False),
        ({"a.py": "import a\n"}, ["first"], True, 1, False),
        ({"a.py": "import b\n", "b.py": "import a\n"}, ["first"], True, 0, False),
        (
            {
                "a.py": "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import b\n",
                "b.py": "import a\n",
            },
            ["first", "second"],
            True,
            1,
            True,
        ),
        (
            {
                "a.py": "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import b\n",
                "b.py": "import a\n",
            },
            ["first", "second"],
            False,
            0,
            False,
        ),
        (
            {
                "a.py": (
                    "import a\nfrom typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import b\n"
                ),
                "b.py": "import a\n",
            },
            ["first", "second"],
            True,
            1,
            False,
        ),
        (
            {"a.py": "import b\n", "b.py": "import c\n", "c.py": "import a\n"},
            ["first", "second"],
            True,
            1,
            False,
        ),
    ],
)
def test_cycles(
    tmp_path: Path, files: dict[str, str], scope: list[str], include: bool, count: int, tc: bool
) -> None:
    g = graph(tmp_path, files)
    data = profile_data()
    data["components"][1]["selectors"].append({"type": "module_exact", "value": "c"})
    data["rules"] = [
        {
            "id": "cycle",
            "type": "forbid_cycles",
            "components": scope,
            "include_type_checking": include,
        }
    ]
    report = evaluate(g, data)
    assert len(report.violations) == count
    assert decode_report(canonical_report(report)) == report
    if count:
        evidence = report.violations[0].evidence
        assert isinstance(evidence, CycleEvidence)
        assert evidence.type_checking_only is tc
        assert len(evidence.module_ids) == len(files)


def test_no_io_determinism(tmp_path: Path) -> None:
    g = graph(tmp_path, {"a.py": "import b\n# secret source content\n", "b.py": "pass\n"})
    p = profile()
    first = DeterministicConstraintEvaluator().evaluate(g, p)
    with (
        patch.object(builtins, "open", side_effect=AssertionError("read")),
        patch.object(Path, "read_bytes", side_effect=AssertionError("read")),
        patch.object(Path, "read_text", side_effect=AssertionError("read")),
        patch.object(subprocess, "run", side_effect=AssertionError("execute")),
        patch.object(subprocess, "Popen", side_effect=AssertionError("execute")),
    ):
        second = DeterministicConstraintEvaluator().evaluate(g, p)
    assert first == second
    assert canonical_report(first) == canonical_report(second)
    assert b"secret source content" not in canonical_report(first)
    assert str(tmp_path).encode() not in canonical_report(first)
    with pytest.raises(FrozenInstanceError):
        first.violations = ()  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        first.assignments[0].component_ids = ()  # type: ignore[misc]
    altered = graph(tmp_path, {"a.py": "pass\n", "b.py": "pass\n"})
    assert evaluate(altered).report_fingerprint != first.report_fingerprint
    assert assign_components(g, p) == first.assignments


@pytest.mark.parametrize("kind", ["profile", "report"])
@pytest.mark.parametrize("mutation", ["schema", "fingerprint", "extra", "duplicate", "nan", "bool"])
def test_artifact_rejection(tmp_path: Path, kind: str, mutation: str) -> None:
    report = evaluate(graph(tmp_path, {"a.py": "import b\n", "b.py": "pass\n"}))
    value = report if kind == "report" else report.profile
    data = asdict(value)
    if mutation == "schema":
        data[f"architecture_{kind}_schema_version"] = "2"
    elif mutation == "fingerprint":
        data[f"{kind}_fingerprint"] = "0" * 64
    elif mutation == "extra":
        data["extra"] = "unknown"
    elif mutation == "bool":
        data["profile" if kind == "report" else "name"] = True
    raw = json.dumps(data).encode()
    if mutation == "duplicate":
        raw = b'{"id":1,"id":2,' + raw[1:]
    elif mutation == "nan":
        raw = b'{"extra":NaN,' + raw[1:]
    with pytest.raises(ValueError):
        (decode_report if kind == "report" else decode_profile)(raw)


@pytest.mark.parametrize(
    "mutation",
    [
        "summary",
        "dangling",
        "location",
        "message",
        "violation-id",
        "assignment",
        "rule",
        "status",
        "unused-edge",
        "component",
        "category",
        "severity",
        "count",
    ],
)
def test_report_invariants_even_rehashed(tmp_path: Path, mutation: str) -> None:
    report = evaluate(graph(tmp_path, {"a.py": "import b\n", "b.py": "pass\n"}))
    data = json.loads(canonical_report(report))
    v = data["violations"][0]
    if mutation == "summary":
        data["summary"]["passed"] = True
    elif mutation == "dangling":
        data["evidence_edges"] = []
    elif mutation == "location":
        v["evidence"]["locations"][0]["line"] = 9
    elif mutation == "message":
        v["message"] = "source content"
    elif mutation == "violation-id":
        v["violation_id"] = "violation:" + "0" * 64
    elif mutation == "assignment":
        data["assignments"][0]["module_id"] = "module:missing"
    elif mutation == "rule":
        v["rule_id"] = "missing"
    elif mutation == "status":
        data["rule_results"][0]["status"] = "disabled"
    elif mutation == "unused-edge":
        data["violations"] = []
    elif mutation == "component":
        v["evidence"]["target_component"] = "first"
    elif mutation == "category":
        v["category"] = "cycle"
    elif mutation == "severity":
        v["severity"] = "info"
    elif mutation == "count":
        v["evidence"]["occurrence_count"] = 99
    from archguard.domain.canonical import canonical_json

    del data["report_fingerprint"]
    data["report_fingerprint"] = hashlib.sha256(canonical_json(data)).hexdigest()
    with pytest.raises(ValueError):
        decode_report(canonical_json(data))


def test_ports_artifacts_and_atomic_failure(tmp_path: Path) -> None:
    profiles = LocalArchitectureProfiles()
    reports = LocalArchitectureReports()
    loader: ArchitectureProfileLoaderPort = profiles
    reader: ArchitectureProfileReaderPort = profiles
    writer: ArchitectureProfileWriterPort = profiles
    report_reader: ArchitectureReportReaderPort = reports
    report_writer: ArchitectureReportWriterPort = reports
    evaluator: ArchitectureConstraintEvaluatorPort = DeterministicConstraintEvaluator()
    yaml_path = tmp_path / "profile.yaml"
    yaml_path.write_text(yaml.safe_dump(profile_data()))
    p = loader.load(yaml_path)
    p1, p2 = tmp_path / "p1.json", tmp_path / "p2.json"
    ref = writer.write(p, p1)
    writer.write(p, p2)
    assert reader.read(p1, ref.sha256) == p
    assert p1.read_bytes() == p2.read_bytes()
    g = graph(tmp_path, {"a.py": "import b\n", "b.py": "pass\n"})
    r = evaluator.evaluate(g, p)
    r1, r2 = tmp_path / "r1.json", tmp_path / "r2.json"
    ref = report_writer.write(r, r1)
    report_writer.write(r, r2)
    assert report_reader.read(r1, ref.sha256) == r
    assert r1.read_bytes() == r2.read_bytes()
    cases: list[tuple[Any, Any, Path]] = [(profiles, p, p1), (reports, r, r1)]
    for adapter, value, path in cases:
        with pytest.raises(ValueError):
            adapter.read(path, "0" * 64)
        with pytest.raises(UnsafePathError):
            adapter.validate_destination(path, sources=(path,))
        with pytest.raises(UnsafePathError):
            adapter.validate_destination(path, tmp_path)
        link = tmp_path / (path.name + "-link")
        link.symlink_to(path)
        with pytest.raises(UnsafePathError):
            adapter.read(link)
        with pytest.raises(UnsafePathError):
            adapter.validate_destination(link)
        with patch("archguard.infrastructure.artifact_io.os.replace", side_effect=OSError):
            with pytest.raises(OSError):
                adapter.write(value, path)
        assert not list(tmp_path.glob(".archguard-*"))
    assert CompileArchitectureProfile(loader, writer).execute(yaml_path, p2).profile == p
    gpath = tmp_path / "graph.json"
    LocalGraphArtifacts().write(g, gpath)
    result = EvaluateArchitecture(LocalGraphArtifacts(), loader, evaluator, report_writer).execute(
        gpath, yaml_path, r2
    )
    assert result.report == r and result.exit_code() == 1
    for output in (yaml_path, gpath):
        with pytest.raises(UnsafePathError):
            EvaluateArchitecture(LocalGraphArtifacts(), loader, evaluator, report_writer).execute(
                gpath, yaml_path, output
            )


def test_cli_complete_workflow(tmp_path: Path) -> None:
    runner = CliRunner()
    p = tmp_path / "profile.yaml"
    p.write_text(yaml.safe_dump(profile_data()))
    g = graph(tmp_path, {"a.py": "import b\n", "b.py": "pass\n"})
    gp, pp, rp = tmp_path / "graph.json", tmp_path / "profile.json", tmp_path / "report.json"
    LocalGraphArtifacts().write(g, gp)

    def invoke(args: list[str], code: int = 0) -> Any:
        result = runner.invoke(app, ["architecture", *args])
        assert result.exit_code == code, (result.output, result.exception)
        assert str(tmp_path) not in result.output
        assert result.output == runner.invoke(app, ["architecture", *args]).output
        return json.loads(result.stdout)

    invoke(["profile", "validate", str(p)])
    invoke(["profile", "compile", str(p), "--output", str(pp)])
    invoke(["profile", "inspect", str(pp)])
    invoke(["evaluate", str(gp), "--profile", str(p), "--output", str(rp)], 1)
    invoke(["inspect", str(rp)])
    violations = invoke(["violations", str(rp)])
    assert len(violations) == 1
    invoke(["explain", str(rp), violations[0]["violation_id"]])
    assert invoke(["violations", str(rp), "--severity", "warning"]) == []
    invoke(["explain", str(rp), "missing"], 2)
    invoke(["evaluate", str(gp), "--profile", str(p), "--output", str(gp)], 3)
    data = profile_data()
    data["rules"] = []
    p.write_text(yaml.safe_dump(data))
    invoke(["evaluate", str(gp), "--profile", str(p), "--output", str(rp)])
    data["components"].append(
        {"id": "overlap", "selectors": [{"type": "module_exact", "value": "a"}]}
    )
    data["assignment"] = {"ambiguous": "warn"}
    p.write_text(yaml.safe_dump(data))
    invoke(["evaluate", str(gp), "--profile", str(p), "--output", str(rp)], 4)
    result = invoke(
        ["evaluate", str(gp), "--profile", str(p), "--output", str(rp), "--allow-partial"]
    )
    assert result["partial"] is True
    for command in (
        ["inspect", "missing"],
        ["violations", "missing"],
        ["explain", "missing", "id"],
        ["profile", "inspect", "missing"],
        ["profile", "validate", "missing"],
        ["profile", "compile", "missing", "--output", str(pp)],
    ):
        invoke(command, 2)


@pytest.mark.parametrize("source_unknown", [False, True])
def test_unknown_source_and_unrelated_dependencies(tmp_path: Path, source_unknown: bool) -> None:
    g = graph(tmp_path, {"a.py": "pass\n", "b.py": "import a\nimport fastapi\n"})
    data = profile_data()
    if source_unknown:
        data["components"][1]["selectors"][0]["value"] = "c"
    report = evaluate(g, data)
    assert report.summary.skipped_rules == int(source_unknown)
    assert not report.violations
    data["rules"] = [
        {
            "id": "external",
            "type": "forbid_external_dependency",
            "source": "first",
            "external": [{"type": "external_exact", "value": "fastapi"}],
        }
    ]
    assert evaluate(g, data).summary.skipped_rules == int(source_unknown)


@pytest.mark.parametrize("kind", ["profile", "report"])
def test_artifact_size_limits(tmp_path: Path, kind: str) -> None:
    report = evaluate(graph(tmp_path, {"a.py": "pass\n"}))
    adapter: Any = LocalArchitectureProfiles() if kind == "profile" else LocalArchitectureReports()
    value = report.profile if kind == "profile" else report
    path = tmp_path / "artifact.json"
    adapter.write(value, path)
    module = "architecture_profiles" if kind == "profile" else "architecture_reports"
    limit = "MAX_PROFILE_BYTES" if kind == "profile" else "MAX_REPORT_BYTES"
    with patch(f"archguard.infrastructure.{module}.{limit}", 16):
        with pytest.raises(ValueError):
            adapter.read(path)
        with pytest.raises(ValueError):
            adapter.write(value, path)
    assert adapter.read(path) == value


@pytest.mark.parametrize(
    "mutation",
    [
        "selectors-not-list",
        "external-unknown",
        "empty-external",
        "empty-cycle",
        "bad-external",
        "bad-assignment-field",
    ],
)
def test_nested_profile_shapes(mutation: str) -> None:
    data = profile_data()
    if mutation == "selectors-not-list":
        data["components"][0]["selectors"] = {}
    elif mutation == "bad-assignment-field":
        data["assignment"] = {"bad": True}
    elif mutation == "empty-cycle":
        data["rules"] = [{"id": "cycle", "type": "forbid_cycles", "components": []}]
    else:
        selectors: list[dict[str, Any]] = [{"type": "external_exact", "value": "fastapi"}]
        if mutation == "external-unknown":
            selectors[0]["extra"] = True
        elif mutation == "empty-external":
            selectors = []
        else:
            selectors[0]["value"] = "fastapi.*"
        data["rules"] = [
            {
                "id": "external",
                "type": "forbid_external_dependency",
                "source": "first",
                "external": selectors,
            }
        ]
    with pytest.raises(ValueError):
        profile(data)


def test_real_example_workflow_and_source_preservation(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    source = root / "examples/python/simple-layered-app"
    before = {p.relative_to(source).as_posix(): p.read_bytes() for p in source.rglob("*.py")}
    runner = CliRunner()
    snapshot, gp, rp = (tmp_path / name for name in ("snapshot.json", "graph.json", "report.json"))
    for args in [
        ["repository", "analyze", str(source), "--source-root", "src", "--output", str(snapshot)],
        ["graph", "build", str(snapshot), "--output", str(gp)],
        [
            "architecture",
            "evaluate",
            str(gp),
            "--profile",
            str(root / "examples/architecture/simple-layered.yaml"),
            "--output",
            str(rp),
        ],
    ]:
        result = runner.invoke(app, args)
        assert result.exit_code == 0, result.output
    passing = LocalArchitectureReports().read(rp)
    assert passing.summary.passed and not passing.summary.partial
    result = runner.invoke(
        app,
        [
            "architecture",
            "evaluate",
            str(gp),
            "--profile",
            str(root / "examples/architecture/simple-layered-violating.yaml"),
            "--output",
            str(rp),
        ],
    )
    assert result.exit_code == 1
    failing = LocalArchitectureReports().read(rp)
    assert failing.summary.total_violation_count == 1
    assert failing.violations[0].rule_id == "application-no-persistence-demo"
    assert before == {
        p.relative_to(source).as_posix(): p.read_bytes() for p in source.rglob("*.py")
    }


def test_repeated_occurrences_with_identical_locations(tmp_path: Path) -> None:
    from archguard.domain.repository import summarize

    g = graph(tmp_path, {"a.py": "import b\n", "b.py": "pass\n"})
    snapshot = LocalRepositoryAnalyzer().analyze(tmp_path / "source", AnalysisOptions())
    first = snapshot.files[0]
    files = (replace(first, imports=first.imports * 2), *snapshot.files[1:])
    snapshot = replace(snapshot, files=files, summary=summarize(files, snapshot.diagnostics))
    repeated = DeterministicGraphBuilder().build(snapshot, GraphBuildOptions())
    report = evaluate(repeated)
    assert report.summary.total_violation_count == 1
    assert report.violations[0].evidence.occurrence_count == 2
    assert {e.occurrence for e in report.evidence_edges} == {1, 2}
    assert report.report_fingerprint != evaluate(g).report_fingerprint


def test_external_overlapping_selectors_aggregate_once(tmp_path: Path) -> None:
    g = graph(tmp_path, {"a.py": "import fastapi\nimport fastapi\n"})
    data = profile_data()
    data["rules"] = [
        {
            "id": "external",
            "type": "forbid_external_dependency",
            "source": "first",
            "external": [
                {"type": "external_exact", "value": "fastapi"},
                {"type": "external_prefix", "value": "fastapi"},
            ],
        }
    ]
    report = evaluate(g, data)
    assert len(report.violations) == 1
    assert report.violations[0].evidence.occurrence_count == 2
    assert len(report.violations[0].evidence.external_selectors) == 2
    assert decode_report(canonical_report(report)) == report
