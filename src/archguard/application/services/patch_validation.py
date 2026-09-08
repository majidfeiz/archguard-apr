"""Isolated candidate validation orchestration through narrow ports."""

from pathlib import Path

from archguard.application.ports.architecture import (
    ArchitectureConstraintEvaluatorPort,
    ArchitectureProfileLoaderPort,
)
from archguard.application.ports.graph import RepositoryGraphBuilderPort
from archguard.application.ports.patch_validation import (
    CandidatePatchInspectorPort,
    CandidateWorkspacePort,
    PatchValidationArtifactPort,
    RepositoryStatePort,
)
from archguard.application.ports.repository import RepositoryAnalyzerPort
from archguard.domain.graph import GraphBuildOptions
from archguard.domain.patch_validation import (
    CandidatePatch,
    PatchDiagnosticCode,
    PatchValidationResult,
    ValidationStatus,
    compare_reports,
    create_validation_result,
)
from archguard.domain.repository import AnalysisOptions


class InspectCandidatePatch:
    def __init__(self, inspector: CandidatePatchInspectorPort) -> None:
        self.inspector = inspector

    def execute(
        self, raw: bytes, allowed_roots: tuple[str, ...] = (), protected_paths: tuple[str, ...] = ()
    ) -> CandidatePatch:
        return self.inspector.inspect(raw, allowed_roots, protected_paths)


class ValidateCandidatePatch:
    def __init__(
        self,
        inspector: CandidatePatchInspectorPort,
        states: RepositoryStatePort,
        workspaces: CandidateWorkspacePort,
        analyzer: RepositoryAnalyzerPort,
        graphs: RepositoryGraphBuilderPort,
        profiles: ArchitectureProfileLoaderPort,
        evaluator: ArchitectureConstraintEvaluatorPort,
        artifacts: PatchValidationArtifactPort,
    ) -> None:
        self.inspector, self.states, self.workspaces = inspector, states, workspaces
        self.analyzer, self.graphs, self.profiles, self.evaluator = (
            analyzer,
            graphs,
            profiles,
            evaluator,
        )
        self.artifacts = artifacts

    def execute(
        self,
        repository: Path,
        raw: bytes,
        profile_path: Path,
        baseline_revision: str,
        analysis_options: AnalysisOptions,
        graph_options: GraphBuildOptions | None = None,
        allowed_roots: tuple[str, ...] = (),
        protected_paths: tuple[str, ...] = (),
        output: Path | None = None,
    ) -> PatchValidationResult:
        graph_options = graph_options or GraphBuildOptions()
        require_clean = getattr(self.states, "require_clean", None)
        before = require_clean(repository) if require_clean else self.states.capture(repository)
        baseline = self.states.resolve_commit(repository, baseline_revision)
        patch = self.inspector.inspect(raw, allowed_roots, protected_paths)
        if not patch.acceptable:
            after = self.states.capture(repository)
            result = create_validation_result(
                ValidationStatus.REJECTED,
                baseline,
                patch,
                before,
                after,
                diagnostic_codes=tuple(d.code for d in patch.diagnostics),
            )
            if output is not None:
                self.artifacts.write(result, output)
            return result
        profile = self.profiles.load(profile_path)
        delta = None
        application_failed = False
        with self.workspaces.workspace(repository, baseline) as workspace:
            baseline_snapshot = self.analyzer.analyze(workspace, analysis_options)
            baseline_graph = self.graphs.build(baseline_snapshot, graph_options)
            baseline_report = self.evaluator.evaluate(baseline_graph, profile)
            if not self.workspaces.check_apply(workspace, raw) or not self.workspaces.apply(
                workspace, raw
            ):
                application_failed = True
            else:
                candidate_snapshot = self.analyzer.analyze(workspace, analysis_options)
                candidate_graph = self.graphs.build(candidate_snapshot, graph_options)
                candidate_report = self.evaluator.evaluate(candidate_graph, profile)
                delta = compare_reports(
                    baseline,
                    patch.patch_fingerprint,
                    baseline_snapshot.repository_fingerprint,
                    candidate_snapshot.repository_fingerprint,
                    baseline_graph.graph_fingerprint,
                    candidate_graph.graph_fingerprint,
                    baseline_report,
                    candidate_report,
                )
        after = self.states.capture(repository)
        result = create_validation_result(
            ValidationStatus.APPLICATION_FAILED
            if application_failed
            else ValidationStatus.COMPLETED,
            baseline,
            patch,
            before,
            after,
            delta=delta,
            diagnostic_codes=(PatchDiagnosticCode.APPLICATION_FAILED,)
            if application_failed
            else (),
            patch_applied=not application_failed,
        )
        if output is not None:
            self.artifacts.write(result, output)
        return result
