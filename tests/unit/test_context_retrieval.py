import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from archguard.application.services.context import (
    CompileRetrievalQuery,
    EvaluateRetrieval,
    RetrieveRepositoryContext,
    normalize_terms,
)
from archguard.application.services.graph_builder import DeterministicGraphBuilder
from archguard.domain.context import (
    CompiledRetrievalQuery,
    RelevanceLabels,
    RetrievalPolicy,
    SelectionState,
)
from archguard.domain.graph import GraphBuildOptions, NodeKind, RepositoryGraph
from archguard.domain.repository import AnalysisOptions, RepositorySnapshot
from archguard.infrastructure.context_artifacts import (
    LocalContextArtifacts,
    LocalRelevanceLabels,
    canonical,
)
from archguard.infrastructure.repository_analyzer import LocalRepositoryAnalyzer


def repository(tmp_path: Path) -> tuple[Path, RepositorySnapshot, RepositoryGraph]:
    root = tmp_path / "repo"
    source = root / "src/app"
    tests = root / "tests"
    source.mkdir(parents=True)
    tests.mkdir()
    (source / "__init__.py").write_text("")
    (source / "model.py").write_text("from .service import run\n\nclass Item:\n    pass\n")
    (source / "repository.py").write_text(
        "from .model import Item\n\ndef load() -> Item:\n    return Item()\n"
    )
    (source / "service.py").write_text(
        "from .repository import load\n\ndef run() -> str:\n    return str(load())\n"
    )
    (source / "unicode.py").write_text('MESSAGE = "سلام"\n')
    (source / "other.py").write_text("def run():\n    return None\n")
    (tests / "test_service.py").write_text("from app.service import run\n")
    options = AnalysisOptions(source_roots=("src", "tests"))
    snapshot = LocalRepositoryAnalyzer().analyze(root, options)
    graph = DeterministicGraphBuilder().build(snapshot, GraphBuildOptions())
    return root, snapshot, graph


def query() -> CompiledRetrievalQuery:
    return CompileRetrievalQuery().execute(
        "q1",
        "ServiceFailure in run()",
        "RuntimeError: broken",
        'File "src/app/service.py", line 4, in run',
        paths=("src/app/service.py",),
        modules=("app.service",),
        symbols=("run",),
        changed_paths=("src/app/repository.py",),
    )


def test_query_normalization_identity_privacy_and_immutability() -> None:
    first = CompileRetrievalQuery().execute("q", "Café ServiceFailure_service")
    second = CompileRetrievalQuery().execute("q", "Cafe\u0301 service_failure Service")
    assert first.normalized_terms == second.normalized_terms
    assert first.query_fingerprint != second.query_fingerprint
    assert "service" in normalize_terms("Service.run service_run")
    assert "Café" not in canonical(first).decode()
    with pytest.raises(dataclasses.FrozenInstanceError):
        first.query_id = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"problem": ""},
        {"problem": "x", "paths": ("../escape.py",)},
        {"problem": "x", "paths": ("/absolute.py",)},
        {"problem": "x", "paths": ("bad\x00.py",)},
        {"problem": "x", "modules": ("not-valid!",)},
        {"problem": "x" * (1024 * 1024 + 1)},
    ],
)
def test_query_rejects_unsafe_or_oversized_input(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        CompileRetrievalQuery().execute("q", **kwargs)  # type: ignore[arg-type]


def test_traceback_paths_and_secret_text_are_sanitized() -> None:
    secret = "TOKEN_ABC_123"
    value = CompileRetrievalQuery().execute(
        "q", "failure", secret, 'File "src/app/service.py", line 2\nFile "/tmp/secret.py", line 1'
    )
    raw = canonical(value)
    assert b"src/app/service.py" in raw
    assert secret.encode() not in raw and b"/tmp/secret.py" not in raw
    assert value.diagnostics[0].code == "unsafe_traceback_path"


def test_retrieval_seed_expansion_scoring_ranking_and_budget(tmp_path: Path) -> None:
    _, snapshot, graph = repository(tmp_path)
    value = (
        RetrieveRepositoryContext(LocalContextArtifacts())
        .execute(snapshot, graph, query(), RetrievalPolicy(max_depth=2, max_source_bytes=10_000))
        .manifest
    )
    assert value.seeds
    assert any(seed.seed_type == "traceback" for seed in value.seeds)
    assert [candidate.rank for candidate in value.candidates] == list(
        range(1, len(value.candidates) + 1)
    )
    assert any(seed.seed_type == "exact_module" for seed in value.seeds)
    assert any(candidate.graph_distance > 0 for candidate in value.candidates)
    assert all(
        candidate.total_score == sum(x.value for x in candidate.score_components)
        for candidate in value.candidates
    )
    assert value.budget.consumed_bytes <= value.policy.max_source_bytes
    assert value.budget.consumed_lines <= value.policy.max_lines
    assert any(
        candidate.selection_state == SelectionState.SELECTED for candidate in value.candidates
    )
    assert all(candidate.decision_reason for candidate in value.candidates)


def test_exact_node_architecture_ambiguous_and_unknown_seeds_on_cycle(tmp_path: Path) -> None:
    _, snapshot, graph = repository(tmp_path)
    node_id = "file:src/app/service.py"
    compiled = CompileRetrievalQuery().execute(
        "explicit",
        "run failure",
        paths=("src/app/missing.py",),
        nodes=(node_id,),
        symbols=("run",),
        architecture_nodes=("module:app.repository",),
    )
    manifest = (
        RetrieveRepositoryContext(LocalContextArtifacts())
        .execute(snapshot, graph, compiled, RetrievalPolicy(max_depth=4))
        .manifest
    )
    assert {"exact_node", "architecture_endpoint", "exact_symbol"} <= {
        seed.seed_type for seed in manifest.seeds
    }
    assert sum(seed.seed_type == "exact_symbol" and seed.ambiguous for seed in manifest.seeds) == 2
    assert any(code.startswith("unknown_path:") for code in manifest.diagnostics)
    assert len({candidate.node_id for candidate in manifest.candidates}) == len(manifest.candidates)


def test_depth_filters_ties_external_and_test_policy(tmp_path: Path) -> None:
    _, snapshot, graph = repository(tmp_path)
    artifacts = LocalContextArtifacts()
    depth_zero = (
        RetrieveRepositoryContext(artifacts)
        .execute(snapshot, graph, query(), RetrievalPolicy(max_depth=0))
        .manifest
    )
    assert all(candidate.graph_distance == 0 for candidate in depth_zero.candidates)
    no_tests = (
        RetrieveRepositoryContext(artifacts)
        .execute(snapshot, graph, query(), RetrievalPolicy(include_tests=False))
        .manifest
    )
    assert all(
        candidate.selection_state == SelectionState.EXCLUDED
        for candidate in no_tests.candidates
        if (candidate.path or "").startswith("tests/")
    )
    assert all(
        candidate.selection_state == SelectionState.EXCLUDED
        for candidate in no_tests.candidates
        if candidate.node_kind == NodeKind.EXTERNAL_MODULE
    )


@pytest.mark.parametrize(
    "policy",
    [
        RetrievalPolicy(max_files=0),
        RetrievalPolicy(max_symbols=0),
        RetrievalPolicy(max_excerpts=0),
        RetrievalPolicy(max_lines=0),
        RetrievalPolicy(max_source_bytes=0),
    ],
)
def test_each_budget_is_a_hard_limit(tmp_path: Path, policy: RetrievalPolicy) -> None:
    _, snapshot, graph = repository(tmp_path)
    manifest = (
        RetrieveRepositoryContext(LocalContextArtifacts())
        .execute(snapshot, graph, query(), policy)
        .manifest
    )
    assert manifest.budget.selected_files <= policy.max_files
    assert manifest.budget.selected_symbols <= policy.max_symbols
    assert manifest.budget.selected_excerpts <= policy.max_excerpts
    assert manifest.budget.consumed_lines <= policy.max_lines
    assert manifest.budget.consumed_bytes <= policy.max_source_bytes


def test_repeated_manifest_and_artifacts_are_identical(tmp_path: Path) -> None:
    _, snapshot, graph = repository(tmp_path)
    artifacts = LocalContextArtifacts()
    outputs = [tmp_path / "one.json", tmp_path / "two.json"]
    for output in outputs:
        RetrieveRepositoryContext(artifacts).execute(
            snapshot, graph, query(), RetrievalPolicy(), output
        )
    assert outputs[0].read_bytes() == outputs[1].read_bytes()
    assert artifacts.read_manifest(outputs[0]).manifest_fingerprint
    data = json.loads(outputs[0].read_bytes())
    data["manifest_fingerprint"] = "0" * 64
    outputs[0].write_text(json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n")
    with pytest.raises(ValueError):
        artifacts.read_manifest(outputs[0])


def test_artifacts_reject_duplicates_unknown_nan_symlinks_and_overwrite(tmp_path: Path) -> None:
    artifacts = LocalContextArtifacts()
    value = CompileRetrievalQuery().execute("q", "problem")
    output = tmp_path / "query.json"
    artifacts.write_query(value, output)
    expected = hashlib.sha256(output.read_bytes()).hexdigest()
    assert artifacts.read_query(output, expected) == value
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        artifacts.read_query(output, "0" * 64)
    with pytest.raises(ValueError, match="already exists"):
        artifacts.write_query(value, output)
    link = tmp_path / "link.json"
    link.symlink_to(output)
    with pytest.raises(ValueError):
        artifacts.read_query(link)
    for raw in (b'{"x":1,"x":2}\n', b'{"x":NaN}\n', b'{"unknown":1}\n'):
        bad = tmp_path / hashlib.sha256(raw).hexdigest()
        bad.write_bytes(raw)
        with pytest.raises(ValueError):
            artifacts.read_query(bad)


def test_exact_retrieval_metrics_and_missing_labels(tmp_path: Path) -> None:
    _, snapshot, graph = repository(tmp_path)
    manifest = (
        RetrieveRepositoryContext(LocalContextArtifacts())
        .execute(snapshot, graph, query(), RetrievalPolicy())
        .manifest
    )
    relevant = manifest.candidates[1].node_id
    labels = RelevanceLabels.create((relevant,))
    evaluation = EvaluateRetrieval(LocalContextArtifacts()).execute(manifest, labels)
    metrics = {item.name: item.value for item in evaluation.metrics}
    assert metrics["MRR"] == "0.500000"
    assert metrics["Hit@1"] == "0.000000"
    assert metrics["Hit@3"] == "1.000000"
    assert metrics["Recall@3"] == "1.000000"
    assert metrics["Precision@3"] == "0.333333"
    missing = EvaluateRetrieval(LocalContextArtifacts()).execute(
        manifest, RelevanceLabels.create(("module:not.present",))
    )
    assert not missing.complete and missing.missing_relevant_references == ("module:not.present",)


def test_labels_are_strict_and_independent(tmp_path: Path) -> None:
    labels = tmp_path / "labels.yaml"
    labels.write_text(
        'retrieval_labels_schema_version: "1"\nrelevant_node_ids:\n  - module:app.service\n'
    )
    assert LocalRelevanceLabels().load(labels).relevant_node_ids == ("module:app.service",)
    labels.write_text('retrieval_labels_schema_version: "1"\nrelevant_node_ids: [x, x]\n')
    with pytest.raises(ValueError):
        LocalRelevanceLabels().load(labels)
