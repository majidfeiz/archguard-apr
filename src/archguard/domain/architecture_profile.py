"""Versioned, immutable explicit architecture specifications; no I/O."""

import hashlib
import re
from dataclasses import asdict, dataclass
from typing import Literal

from archguard.domain.canonical import canonical_json
from archguard.domain.enums import Severity
from archguard.domain.repository import check, digest, dotted_name, safe_path

PROFILE_SCHEMA_VERSION = "1"
MAX_COMPONENTS = 256
MAX_SELECTORS = 256
MAX_RULES = 2048
type PolicyAction = Literal["ignore", "warn", "error"]


def identifier(value: str) -> None:
    check(re.fullmatch(r"[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*", value) is not None, "invalid ID")
    check(len(value) <= 128, "ID too long")


def description_text(value: str | None) -> None:
    check(
        value is None or (len(value) <= 4096 and all(ord(c) >= 32 for c in value)),
        "invalid descriptive text",
    )


@dataclass(frozen=True, order=True)
class ModuleSelector:
    type: Literal["module_exact", "module_prefix", "path_exact", "path_prefix"]
    value: str

    def __post_init__(self) -> None:
        check(
            self.type in {"module_exact", "module_prefix", "path_exact", "path_prefix"},
            "invalid selector",
        )
        check(len(self.value) <= 1024, "selector too long")
        if self.type.startswith("module_"):
            check(dotted_name(self.value), "invalid module selector")
        else:
            safe_path(self.value)
            check(not any(c in self.value for c in "*?[]"), "unsupported path selector")

    def matches(self, module: str, path: str) -> bool:
        value, separator = (module, ".") if self.type.startswith("module_") else (path, "/")
        return value == self.value or (
            self.type.endswith("_prefix") and value.startswith(self.value + separator)
        )


@dataclass(frozen=True, order=True)
class ExternalSelector:
    type: Literal["external_exact", "external_prefix"]
    value: str

    def __post_init__(self) -> None:
        check(self.type in {"external_exact", "external_prefix"}, "invalid external selector")
        check(len(self.value) <= 1024 and dotted_name(self.value), "invalid external name")

    def matches(self, name: str) -> bool:
        return name == self.value or (
            self.type == "external_prefix" and name.startswith(self.value + ".")
        )


@dataclass(frozen=True)
class ArchitectureComponent:
    id: str
    selectors: tuple[ModuleSelector, ...]

    def __post_init__(self) -> None:
        identifier(self.id)
        check(0 < len(self.selectors) <= MAX_SELECTORS, "invalid selector count")
        object.__setattr__(self, "selectors", tuple(sorted(set(self.selectors))))


@dataclass(frozen=True)
class ProfilePolicy:
    unassigned: PolicyAction = "warn"
    ambiguous: PolicyAction = "error"

    def __post_init__(self) -> None:
        check(self.unassigned in {"ignore", "warn", "error"}, "invalid assignment policy")
        check(self.ambiguous in {"ignore", "warn", "error"}, "invalid assignment policy")


@dataclass(frozen=True, kw_only=True)
class RuleControls:
    id: str
    severity: Severity = Severity.ERROR
    enabled: bool = True
    description: str | None = None
    include_type_checking: bool = True

    def __post_init__(self) -> None:
        identifier(self.id)
        check(isinstance(self.severity, Severity), "invalid severity")
        check(
            type(self.enabled) is bool and type(self.include_type_checking) is bool,
            "invalid rule control",
        )
        description_text(self.description)


@dataclass(frozen=True, kw_only=True)
class ForbidDependency(RuleControls):
    type: Literal["forbid_dependency"] = "forbid_dependency"
    source: str
    target: str

    def __post_init__(self) -> None:
        super().__post_init__()
        check(self.type == "forbid_dependency", "invalid rule type")
        identifier(self.source)
        identifier(self.target)


@dataclass(frozen=True, kw_only=True)
class AllowOnlyDependencies(RuleControls):
    type: Literal["allow_only_dependencies"] = "allow_only_dependencies"
    source: str
    allowed: tuple[str, ...]

    def __post_init__(self) -> None:
        super().__post_init__()
        check(self.type == "allow_only_dependencies", "invalid rule type")
        identifier(self.source)
        normalize_references(self, "allowed", self.allowed)


@dataclass(frozen=True, kw_only=True)
class ForbidExternalDependency(RuleControls):
    type: Literal["forbid_external_dependency"] = "forbid_external_dependency"
    source: str
    external: tuple[ExternalSelector, ...]

    def __post_init__(self) -> None:
        super().__post_init__()
        check(self.type == "forbid_external_dependency", "invalid rule type")
        identifier(self.source)
        check(0 < len(self.external) <= MAX_SELECTORS, "invalid external selector count")
        object.__setattr__(self, "external", tuple(sorted(set(self.external))))


@dataclass(frozen=True, kw_only=True)
class ForbidCycles(RuleControls):
    type: Literal["forbid_cycles"] = "forbid_cycles"
    components: tuple[str, ...]

    def __post_init__(self) -> None:
        super().__post_init__()
        check(self.type == "forbid_cycles", "invalid rule type")
        check(bool(self.components), "cycle scope cannot be empty")
        normalize_references(self, "components", self.components)


def normalize_references(owner: object, field: str, values: tuple[str, ...]) -> None:
    check(len(values) <= MAX_COMPONENTS, "too many component references")
    for value in values:
        identifier(value)
    object.__setattr__(owner, field, tuple(sorted(set(values))))


type ArchitectureRule = (
    ForbidDependency | AllowOnlyDependencies | ForbidExternalDependency | ForbidCycles
)


def referenced_components(rule: ArchitectureRule) -> tuple[str, ...]:
    if isinstance(rule, ForbidCycles):
        return rule.components
    if isinstance(rule, ForbidDependency):
        return (rule.source, rule.target)
    if isinstance(rule, AllowOnlyDependencies):
        return (rule.source, *rule.allowed)
    return (rule.source,)


@dataclass(frozen=True)
class ArchitectureProfile:
    architecture_profile_schema_version: str
    id: str
    name: str
    description: str | None
    components: tuple[ArchitectureComponent, ...]
    rules: tuple[ArchitectureRule, ...]
    assignment: ProfilePolicy
    profile_fingerprint: str

    def __post_init__(self) -> None:
        check(
            self.architecture_profile_schema_version == PROFILE_SCHEMA_VERSION,
            "unsupported profile schema",
        )
        identifier(self.id)
        description_text(self.name)
        check(bool(self.name), "profile name is required")
        description_text(self.description)
        check(0 < len(self.components) <= MAX_COMPONENTS, "invalid component count")
        check(len(self.rules) <= MAX_RULES, "too many rules")
        for field in ("components", "rules"):
            values = getattr(self, field)
            check(len({v.id for v in values}) == len(values), "duplicate ID")
            object.__setattr__(self, field, tuple(sorted(values, key=lambda v: v.id)))
        component_ids = {c.id for c in self.components}
        check(
            all(set(referenced_components(r)) <= component_ids for r in self.rules),
            "undefined component",
        )
        digest(self.profile_fingerprint)
        check(self.profile_fingerprint == profile_identity(self), "profile fingerprint mismatch")

    @classmethod
    def create(
        cls,
        id: str,
        name: str,
        components: tuple[ArchitectureComponent, ...],
        rules: tuple[ArchitectureRule, ...],
        assignment: ProfilePolicy | None = None,
        description: str | None = None,
        architecture_profile_schema_version: str = "1",
    ) -> "ArchitectureProfile":
        assignment = assignment or ProfilePolicy()
        ordered_components = tuple(sorted(components, key=lambda c: c.id))
        ordered_rules = tuple(sorted(rules, key=lambda r: r.id))
        data = {
            "architecture_profile_schema_version": architecture_profile_schema_version,
            "id": id,
            "name": name,
            "description": description,
            "components": [asdict(c) for c in ordered_components],
            "rules": [asdict(r) for r in ordered_rules],
            "assignment": asdict(assignment),
        }
        return cls(
            architecture_profile_schema_version,
            id,
            name,
            description,
            ordered_components,
            ordered_rules,
            assignment,
            hashlib.sha256(canonical_json(data)).hexdigest(),
        )


def profile_identity(profile: ArchitectureProfile) -> str:
    data = asdict(profile)
    del data["profile_fingerprint"]
    return hashlib.sha256(canonical_json(data)).hexdigest()
