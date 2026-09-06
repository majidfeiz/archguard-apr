"""Deterministic structural queries; cycles are not architecture violations."""

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Literal

from archguard.domain.graph import (
    EdgeKind,
    GraphNode,
    GraphSummary,
    NodeKind,
    RepositoryGraph,
    Resolution,
)
from archguard.domain.graph_algorithms import components as components


@dataclass(frozen=True)
class ModuleComponent:
    nodes: tuple[str, ...]
    cyclic: bool
    type_checking_only: bool


class QueryRepositoryGraph:
    def __init__(self, graph: RepositoryGraph) -> None:
        self.graph = graph
        self.nodes = {node.identifier: node for node in graph.nodes}
        self.outgoing: dict[str, list[int]] = defaultdict(list)
        self.incoming: dict[str, list[int]] = defaultdict(list)
        for index, edge in enumerate(graph.edges):
            self.outgoing[edge.source].append(index)
            self.incoming[edge.target].append(index)

    def node(self, identifier: str) -> GraphNode:
        if identifier not in self.nodes:
            raise ValueError("unknown graph node")
        return self.nodes[identifier]

    def neighbors(
        self,
        identifier: str,
        direction: Literal["incoming", "outgoing"] = "outgoing",
        kind: EdgeKind | None = None,
    ) -> tuple[str, ...]:
        self.node(identifier)
        if direction not in {"incoming", "outgoing"}:
            raise ValueError("invalid neighbor direction")
        indices = (
            self.incoming[identifier] if direction == "incoming" else self.outgoing[identifier]
        )
        return tuple(
            sorted(
                {
                    edge.source if direction == "incoming" else edge.target
                    for i in indices
                    if (edge := self.graph.edges[i]) and (kind is None or edge.kind == kind)
                }
            )
        )

    def dependencies(self, module: str) -> tuple[str, ...]:
        self.require_module(module)
        return self.neighbors(module, kind=EdgeKind.IMPORTS)

    def reverse_dependencies(self, module: str) -> tuple[str, ...]:
        self.require_module(module)
        return self.neighbors(module, "incoming", EdgeKind.IMPORTS)

    def require_module(self, identifier: str) -> None:
        if self.node(identifier).kind != NodeKind.MODULE:
            raise ValueError("query requires an internal module node")

    def shortest_path(
        self, start: str, end: str, kind: EdgeKind | None = None
    ) -> tuple[str, ...] | None:
        self.node(start)
        self.node(end)
        parents: dict[str, str | None] = {start: None}
        pending = deque([start])
        while pending:
            current = pending.popleft()
            if current == end:
                path = [end]
                while (parent := parents[path[-1]]) is not None:
                    path.append(parent)
                return tuple(reversed(path))
            for child in self.neighbors(current, kind=kind):
                if child not in parents:
                    parents[child] = current
                    pending.append(child)
        return None

    def module_components(self, runtime_only: bool = False) -> tuple[ModuleComponent, ...]:
        all_edges: dict[str, set[str]] = {
            node.identifier: set() for node in self.graph.nodes if node.kind == NodeKind.MODULE
        }
        runtime = {node: set[str]() for node in all_edges}
        for edge in self.graph.edges:
            if edge.resolution == Resolution.INTERNAL:
                all_edges[edge.source].add(edge.target)
                assert edge.import_record is not None
                if not edge.import_record.type_checking:
                    runtime[edge.source].add(edge.target)
        runtime_cycles = {
            node
            for group in components(runtime)
            if len(group) > 1 or group[0] in runtime[group[0]]
            for node in group
        }
        adjacency = runtime if runtime_only else all_edges
        return tuple(
            ModuleComponent(
                group,
                cyclic := len(group) > 1 or group[0] in adjacency[group[0]],
                cyclic and not runtime_only and not any(n in runtime_cycles for n in group),
            )
            for group in components(adjacency)
        )

    def cycles(self, runtime_only: bool = False) -> tuple[ModuleComponent, ...]:
        return tuple(group for group in self.module_components(runtime_only) if group.cyclic)

    def statistics(self) -> GraphSummary:
        return self.graph.summary
