"""Bounded safe YAML loading and strict canonical profile JSON persistence."""

import hashlib
import json
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

import yaml
from pydantic import TypeAdapter
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode
from yaml.tokens import AliasToken, AnchorToken

from archguard.domain.architecture_profile import (
    AllowOnlyDependencies,
    ArchitectureComponent,
    ArchitectureProfile,
    ArchitectureRule,
    ExternalSelector,
    ForbidCycles,
    ForbidDependency,
    ForbidExternalDependency,
    ModuleSelector,
    ProfilePolicy,
)
from archguard.domain.canonical import canonical_json
from archguard.domain.enums import ArtifactKind
from archguard.domain.models import ArtifactReference
from archguard.infrastructure.artifact_io import atomic_write, destination_path, read_artifact
from archguard.infrastructure.graph_artifacts import LocalGraphArtifacts
from archguard.infrastructure.json_codec import unique_object

MAX_PROFILE_BYTES = 1024 * 1024
RULE_CLASSES = {
    "forbid_dependency": ForbidDependency,
    "allow_only_dependencies": AllowOnlyDependencies,
    "forbid_external_dependency": ForbidExternalDependency,
    "forbid_cycles": ForbidCycles,
}


def yaml_shape(node: Node, depth: int = 0) -> None:
    if depth > 16:
        raise ValueError("profile nesting exceeds limit")
    if isinstance(node, MappingNode):
        seen: set[str] = set()
        for key, value in node.value:
            if not isinstance(key, ScalarNode) or key.tag != "tag:yaml.org,2002:str":
                raise ValueError("profile keys must be strings")
            if key.value in seen:
                raise ValueError("duplicate YAML key")
            seen.add(key.value)
            yaml_shape(value, depth + 1)
    elif isinstance(node, SequenceNode):
        for value in node.value:
            yaml_shape(value, depth + 1)


def shape(data: Any, allowed: set[str]) -> None:
    if not isinstance(data, dict) or any(type(k) is not str or k not in allowed for k in data):
        raise ValueError("unknown field or invalid object")


def selectors_shape(data: Any, external: bool = False) -> None:
    if not isinstance(data, list):
        raise ValueError("selectors must be arrays")
    for selector in data:
        shape(selector, {f.name for f in fields(ExternalSelector if external else ModuleSelector)})


def compile_data(data: Any) -> ArchitectureProfile:
    shape(data, {f.name for f in fields(ArchitectureProfile)} - {"profile_fingerprint"})
    components = []
    for item in data["components"]:
        shape(item, {"id", "selectors"})
        selectors_shape(item["selectors"])
        components.append(
            TypeAdapter(ArchitectureComponent).validate_json(canonical_json(item), strict=True)
        )
    rules: list[ArchitectureRule] = []
    for item in data["rules"]:
        if not isinstance(item, dict) or item.get("type") not in RULE_CLASSES:
            raise ValueError("unknown rule type")
        cls = RULE_CLASSES[item["type"]]
        shape(item, {f.name for f in fields(cls)})
        if "external" in item:
            selectors_shape(item["external"], True)
        rules.append(TypeAdapter(ArchitectureRule).validate_json(canonical_json(item), strict=True))
    policy = data.get("assignment", {})
    shape(policy, {"unassigned", "ambiguous"})
    assignment = TypeAdapter(ProfilePolicy).validate_json(canonical_json(policy), strict=True)
    # Validate scalar types without coercing YAML numbers/bools into strings.
    for key in ("id", "name", "architecture_profile_schema_version"):
        if type(data[key]) is not str:
            raise ValueError("profile scalar must be a string")
    if data.get("description") is not None and type(data["description"]) is not str:
        raise ValueError("description must be a string")
    return ArchitectureProfile.create(
        data["id"],
        data["name"],
        tuple(components),
        tuple(rules),
        assignment,
        data.get("description"),
        data["architecture_profile_schema_version"],
    )


def load_profile_yaml(raw: bytes) -> ArchitectureProfile:
    try:
        if len(raw) > MAX_PROFILE_BYTES:
            raise ValueError("profile exceeds byte limit")
        if any(isinstance(token, (AliasToken, AnchorToken)) for token in yaml.scan(raw)):
            raise ValueError("YAML anchors and aliases are unsupported")
        node = yaml.compose(raw, Loader=yaml.SafeLoader)
        if node is None:
            raise ValueError("empty profile")
        yaml_shape(node)
        return compile_data(yaml.safe_load(raw))
    except (yaml.YAMLError, ValueError, TypeError, KeyError, RecursionError, AttributeError):
        raise ValueError("invalid architecture profile YAML, schema or limits") from None


def canonical_profile(profile: ArchitectureProfile) -> bytes:
    return canonical_json(asdict(profile))


def decode_profile(raw: bytes) -> ArchitectureProfile:
    try:
        data = json.loads(raw, object_pairs_hook=unique_object)
        profile = TypeAdapter(ArchitectureProfile).validate_json(raw, strict=True)
        if json.loads(canonical_profile(profile)) != data:
            raise ValueError("noncanonical profile shape")
        return profile
    except (ValueError, TypeError, KeyError, RecursionError, AttributeError):
        raise ValueError("invalid architecture profile artifact") from None


class LocalArchitectureProfiles:
    def load(self, source: Path) -> ArchitectureProfile:
        return load_profile_yaml(read_artifact(source, None, MAX_PROFILE_BYTES))

    def validate_destination(
        self,
        destination: Path,
        protected_root: Path | None = None,
        sources: tuple[Path, ...] = (),
    ) -> None:
        LocalGraphArtifacts().validate_destination(destination, protected_root)
        for source in sources:
            LocalGraphArtifacts().validate_destination(destination, source=source)

    def write(self, profile: ArchitectureProfile, destination: Path) -> ArtifactReference:
        target = destination_path(destination)
        raw = canonical_profile(profile)
        if len(raw) > MAX_PROFILE_BYTES:
            raise ValueError("canonical profile exceeds byte limit")
        atomic_write(target, raw)
        return ArtifactReference(
            target.name, ArtifactKind.ARCHITECTURE_PROFILE, hashlib.sha256(raw).hexdigest()
        )

    def read(self, source: Path, expected_sha256: str | None = None) -> ArchitectureProfile:
        return decode_profile(read_artifact(source, expected_sha256, MAX_PROFILE_BYTES))
