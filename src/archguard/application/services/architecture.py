"""Architecture workflow orchestration through independent ports."""

from dataclasses import dataclass
from pathlib import Path

from archguard.application.ports.architecture import (
    ArchitectureConstraintEvaluatorPort,
    ArchitectureProfileLoaderPort,
    ArchitectureProfileWriterPort,
    ArchitectureReportWriterPort,
)
from archguard.application.ports.graph import GraphArtifactReaderPort
from archguard.domain.architecture_profile import ArchitectureProfile
from archguard.domain.architecture_report import ArchitectureReport, ArchitectureViolation
from archguard.domain.enums import Severity
from archguard.domain.models import ArtifactReference


@dataclass(frozen=True)
class ProfileCompilationResult:
    profile: ArchitectureProfile
    artifact: ArtifactReference


class CompileArchitectureProfile:
    def __init__(
        self, loader: ArchitectureProfileLoaderPort, writer: ArchitectureProfileWriterPort
    ) -> None:
        self.loader, self.writer = loader, writer

    def execute(
        self, source: Path, output: Path, protected_root: Path | None = None
    ) -> ProfileCompilationResult:
        self.writer.validate_destination(output, protected_root, (source,))
        profile = self.loader.load(source)
        return ProfileCompilationResult(profile, self.writer.write(profile, output))


@dataclass(frozen=True)
class ArchitectureEvaluationResult:
    report: ArchitectureReport
    artifact: ArtifactReference

    def exit_code(self, allow_partial: bool = False) -> int:
        if self.report.summary.partial and not allow_partial:
            return 4
        return 0 if self.report.summary.passed else 1


class EvaluateArchitecture:
    def __init__(
        self,
        graphs: GraphArtifactReaderPort,
        profiles: ArchitectureProfileLoaderPort,
        evaluator: ArchitectureConstraintEvaluatorPort,
        reports: ArchitectureReportWriterPort,
    ) -> None:
        self.graphs, self.profiles, self.evaluator, self.reports = (
            graphs,
            profiles,
            evaluator,
            reports,
        )

    def execute(
        self, source: Path, profile: Path, output: Path, protected_root: Path | None = None
    ) -> ArchitectureEvaluationResult:
        self.reports.validate_destination(output, protected_root, (source, profile))
        report = self.evaluator.evaluate(self.graphs.read(source), self.profiles.load(profile))
        return ArchitectureEvaluationResult(report, self.reports.write(report, output))


def select_violations(
    report: ArchitectureReport, severity: Severity | None = None
) -> tuple[ArchitectureViolation, ...]:
    return tuple(v for v in report.violations if severity is None or v.severity == severity)


def explain_violation(report: ArchitectureReport, identifier: str) -> ArchitectureViolation:
    for violation in report.violations:
        if violation.violation_id == identifier:
            return violation
    raise ValueError("unknown violation ID")
