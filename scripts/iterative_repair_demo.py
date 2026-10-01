"""Offline Phase 10 refinement demonstration; scripted evidence, no provider or target execution."""

import argparse
import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path

from archguard.application.services.repair_loop import add_candidate, select
from archguard.domain.canonical import canonical_json
from archguard.domain.orchestration import AgentRole, ArtifactReference
from archguard.domain.repair import (
    LINEAGE_SCHEMA,
    REPAIR_FEEDBACK_SCHEMA,
    REPAIR_RESULT_SCHEMA,
    CandidateLineage,
    PatchCandidate,
    RepairFeedback,
    RepairIntent,
    RepairResult,
    RepairStatus,
    RepairTask,
    ValidationEvidence,
)
from archguard.infrastructure.artifact_io import atomic_write, destination_path
from archguard.infrastructure.repair import load_repair_task, make_candidate

PATCH_A = b"""diff --git a/src/demo/__init__.py b/src/demo/__init__.py
--- a/src/demo/__init__.py
+++ b/src/demo/__init__.py
@@ -1 +1 @@
-SAFE = True
+SAFE = False
"""
PATCH_B = b"""diff --git a/src/demo/service.py b/src/demo/service.py
--- a/src/demo/service.py
+++ b/src/demo/service.py
@@ -1 +1 @@
-VALUE = 1
+VALUE = None
"""
PATCH_C = b"""diff --git a/src/demo/service.py b/src/demo/service.py
--- a/src/demo/service.py
+++ b/src/demo/service.py
@@ -1 +1 @@
-VALUE = 1
+VALUE = 2
"""


def artifact(kind: str, char: str) -> ArtifactReference:
    return ArtifactReference(kind, char * 64)


def evidence(
    candidate_id: str, *, architecture: bool, regressions: int, fixed: int, persistent: int
) -> ValidationEvidence:
    return ValidationEvidence(
        candidate_id,
        True,
        True,
        architecture,
        int(not architecture),
        regressions,
        fixed,
        persistent,
        True,
        False,
        False,
        True,
        128,
        1,
    )


def write(
    path: Path,
    value: RepairTask
    | PatchCandidate
    | RepairFeedback
    | CandidateLineage
    | ValidationEvidence
    | RepairResult,
) -> None:
    atomic_write(destination_path(path), canonical_json(asdict(value)))


def run(task_path: Path, output: Path) -> dict[str, object]:
    task = load_repair_task(task_path)
    output.mkdir(parents=False)
    write(output / "task.json", task)

    def make(
        identifier: str,
        round_number: int,
        parent: str | None,
        raw: bytes,
        intent: RepairIntent,
    ) -> PatchCandidate:
        value, _ = make_candidate(
            task=task,
            run_id="offline-demo",
            candidate_id=identifier,
            repair_round=round_number,
            parent_candidate_id=parent,
            role=AgentRole.PATCH_PROPOSER,
            provider_invocation=artifact("provider_invocation", "d"),
            raw_patch_reference=artifact("patch", "e"),
            raw=raw,
            intent=intent,
            assumptions=(),
        )
        return value

    a = make("candidate-a", 1, None, PATCH_A, RepairIntent.MINIMAL_LOCAL_FIX)
    b = make("candidate-b", 1, None, PATCH_B, RepairIntent.CONTROL_FLOW)
    c = make("candidate-c", 2, "candidate-b", PATCH_C, RepairIntent.DATA_VALIDATION)
    lineage = CandidateLineage(LINEAGE_SCHEMA, "offline-demo", ())
    for candidate in (a, b, c):
        lineage = add_candidate(lineage, candidate)
        write(output / f"{candidate.candidate_id}.json", candidate)
    feedback = RepairFeedback(
        REPAIR_FEEDBACK_SCHEMA,
        "candidate-b",
        "functional_delta",
        ("functional_regression",),
        ("tests/test_service.py::test_regression",),
        "Verified regression summary; complete raw logs omitted.",
        1,
        2,
        ("submit_replacement_patch",),
    )
    write(output / "feedback-candidate-b.json", feedback)
    validations = (
        (b, evidence("candidate-b", architecture=True, regressions=1, fixed=1, persistent=0)),
        (c, evidence("candidate-c", architecture=True, regressions=0, fixed=1, persistent=0)),
    )
    selected = select(task, validations)
    if selected != "candidate-c":
        raise RuntimeError("offline scenario selection failed")
    lineage = replace(lineage, selected_candidate_id=selected, lineage_fingerprint="")
    write(output / "lineage.json", lineage)
    for _, item in validations:
        write(output / f"validation-{item.candidate_id}.json", item)
    result = RepairResult(
        REPAIR_RESULT_SCHEMA,
        task.task_fingerprint,
        "offline-demo",
        RepairStatus.REPAIRED,
        "accepted_candidate",
        selected,
        (selected,),
        (("candidate-a", ("protected_path",)), ("candidate-b", ("functional_regression",))),
        lineage.lineage_fingerprint,
        tuple(item.evidence_fingerprint for _, item in validations),
        (),
        ("Selected fixture tests do not prove complete correctness.",),
    )
    write(output / "result.json", result)
    hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(output.iterdir())
    }
    return {
        "scenario": "offline_scripted_engineering_check",
        "selected_candidate_id": selected,
        "provider_calls": 0,
        "artifact_sha256": hashes,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.task, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
