"""Build one canonical source-free V2.1B identity archive after cleanup."""

import argparse
from pathlib import Path

from archguard.domain.v2_identity import (
    ACQUISITION_CEILING_BYTES,
    AUTHORIZED_PROJECT,
    AUTHORIZED_REPOSITORY,
    AUTHORIZED_REVISION,
    AUTHORIZED_TASK,
    IDENTITY_SCHEMA,
)
from archguard.infrastructure.v2_identity_archive import write_identity_archive


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resolved-revision", required=True)
    parser.add_argument("--object-format", required=True)
    parser.add_argument("--root-tree", required=True)
    parser.add_argument("--ls-tree-sha256", required=True)
    parser.add_argument("--entry-count", type=int, required=True)
    parser.add_argument("--acquisition-bytes", type=int, required=True)
    parser.add_argument("--github-run-id", required=True)
    parser.add_argument("--github-job", required=True)
    parser.add_argument("--runner-os", required=True)
    parser.add_argument("--runner-arch", required=True)
    arguments = parser.parse_args()
    write_identity_archive(
        arguments.output,
        {
            "schema": IDENTITY_SCHEMA,
            "project": AUTHORIZED_PROJECT,
            "task_id": AUTHORIZED_TASK,
            "authorized_repository_url": AUTHORIZED_REPOSITORY,
            "requested_revision": AUTHORIZED_REVISION,
            "resolved_revision": arguments.resolved_revision,
            "git_object_format": arguments.object_format,
            "root_tree_object_id": arguments.root_tree,
            "ls_tree_sha256": arguments.ls_tree_sha256,
            "tree_entry_count": arguments.entry_count,
            "acquisition_byte_count": arguments.acquisition_bytes,
            "acquisition_ceiling": ACQUISITION_CEILING_BYTES,
            "checkout_performed": False,
            "source_files_opened": False,
            "hooks_executed": False,
            "submodules_initialized": False,
            "lfs_smudge_executed": False,
            "target_code_executed": False,
            "provider_calls": 0,
            "scientific_executions": 0,
            "github_run_id": arguments.github_run_id,
            "github_job_identity": arguments.github_job,
            "runner_os": arguments.runner_os,
            "runner_architecture": arguments.runner_arch,
            "cleanup_result": "SUCCEEDED",
        },
    )


if __name__ == "__main__":
    main()
