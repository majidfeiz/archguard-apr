"""Immutable source-free V2.1B Git tree identity evidence."""

from dataclasses import dataclass

from archguard.domain.repository import check, digest

IDENTITY_SCHEMA = "archguard.v2-fixed-tree-identity/v1"
AUTHORIZED_PROJECT = "PySnooper"
AUTHORIZED_TASK = "PySnooper-2"
AUTHORIZED_REPOSITORY = "https://github.com/cool-RR/PySnooper.git"
AUTHORIZED_REVISION = "814abc34a098c1b98cb327105ac396f985d2413e"
TASK_MANIFEST_FINGERPRINT = "400834ccce3146e41c6f30aedc334b017028b48bc14f7a08608ba86277efeba0"
ACQUISITION_CEILING_BYTES = 67_108_864


@dataclass(frozen=True)
class FixedTreeIdentity:
    schema: str
    project: str
    task_id: str
    authorized_repository_url: str
    requested_revision: str
    resolved_revision: str
    git_object_format: str
    root_tree_object_id: str
    ls_tree_sha256: str
    tree_entry_count: int
    acquisition_byte_count: int
    acquisition_ceiling: int
    checkout_performed: bool
    source_files_opened: bool
    hooks_executed: bool
    submodules_initialized: bool
    lfs_smudge_executed: bool
    target_code_executed: bool
    provider_calls: int
    scientific_executions: int
    github_run_id: str
    github_job_identity: str
    runner_os: str
    runner_architecture: str
    cleanup_result: str
    fingerprint: str

    def __post_init__(self) -> None:
        check(self.schema == IDENTITY_SCHEMA, "unsupported identity schema")
        check(self.project == AUTHORIZED_PROJECT, "wrong project")
        check(self.task_id == AUTHORIZED_TASK, "wrong task")
        check(self.authorized_repository_url == AUTHORIZED_REPOSITORY, "wrong repository")
        check(self.requested_revision == AUTHORIZED_REVISION, "wrong requested revision")
        check(self.resolved_revision == AUTHORIZED_REVISION, "wrong resolved revision")
        check(self.git_object_format in {"sha1", "sha256"}, "invalid Git object format")
        object_id_length = 40 if self.git_object_format == "sha1" else 64
        check(
            len(self.root_tree_object_id) == object_id_length
            and all(character in "0123456789abcdef" for character in self.root_tree_object_id),
            "invalid root tree object ID",
        )
        digest(self.ls_tree_sha256)
        digest(self.fingerprint)
        check(self.tree_entry_count > 0, "invalid tree entry count")
        check(
            0 < self.acquisition_byte_count <= self.acquisition_ceiling,
            "invalid acquisition byte count",
        )
        check(
            self.acquisition_ceiling == ACQUISITION_CEILING_BYTES,
            "invalid acquisition ceiling",
        )
        check(
            not any(
                (
                    self.checkout_performed,
                    self.source_files_opened,
                    self.hooks_executed,
                    self.submodules_initialized,
                    self.lfs_smudge_executed,
                    self.target_code_executed,
                )
            ),
            "forbidden target operation recorded",
        )
        check(self.provider_calls == 0, "provider call recorded")
        check(self.scientific_executions == 0, "scientific execution recorded")
        check(self.github_run_id.isdecimal(), "invalid GitHub run ID")
        check(
            self.github_job_identity == "identity-only-acquisition",
            "invalid GitHub job identity",
        )
        check(self.runner_os == "Linux", "unsupported runner OS")
        check(self.runner_architecture in {"X64", "x86_64"}, "unsupported runner architecture")
        check(self.cleanup_result == "SUCCEEDED", "cleanup failed")
