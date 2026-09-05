"""Conservative import resolution using snapshot-derived module ownership only."""

from collections.abc import Mapping

from archguard.domain.graph import GraphBuildOptions, GraphDiagnosticCode, GraphFile, Resolution
from archguard.domain.repository import ImportKind, ImportSnapshot


def resolve_import(
    file: GraphFile, record: ImportSnapshot, owners: Mapping[str, int], options: GraphBuildOptions
) -> tuple[Resolution, str | None, GraphDiagnosticCode | None]:
    if file.module_name is None:
        return Resolution.UNRESOLVED, None, GraphDiagnosticCode.INVALID_IMPORTER
    if owners[file.module_name] != 1:
        return Resolution.AMBIGUOUS, None, GraphDiagnosticCode.AMBIGUOUS_IMPORT
    base = record.raw_module
    if record.relative_level:
        package = (
            file.module_name.split(".")
            if file.package_initializer
            else file.module_name.split(".")[:-1]
        )
        if record.relative_level > len(package):
            return Resolution.UNRESOLVED, None, GraphDiagnosticCode.BEYOND_ROOT
        package = package[: len(package) - record.relative_level + 1]
        base = ".".join(package + ([base] if base else []))
    candidates = [base]
    if record.kind == ImportKind.FROM and not record.wildcard:
        candidates.insert(0, base + "." + str(record.imported_name))
    for name in candidates:
        count = owners.get(name, 0)
        if count > 1:
            return Resolution.AMBIGUOUS, None, GraphDiagnosticCode.AMBIGUOUS_IMPORT
        if count == 1:
            return Resolution.INTERNAL, "module:" + name, None
    if record.relative_level:
        return Resolution.UNRESOLVED, None, GraphDiagnosticCode.UNRESOLVED_RELATIVE
    external = base if options.external_names == "full_module" else base.split(".")[0]
    return Resolution.EXTERNAL, "external-module:" + external, None
