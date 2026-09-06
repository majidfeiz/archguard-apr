"""Shared deterministic iterative SCC algorithm."""


def components(adjacency: dict[str, set[str]]) -> tuple[tuple[str, ...], ...]:
    """Iterative Kosaraju: avoid recursion limits on long dependency chains."""
    visited: set[str] = set()
    finished: list[str] = []
    for root in sorted(adjacency):
        if root in visited:
            continue
        stack = [(root, False)]
        while stack:
            node, exiting = stack.pop()
            if exiting:
                finished.append(node)
            elif node not in visited:
                visited.add(node)
                stack.append((node, True))
                stack.extend(
                    (child, False)
                    for child in sorted(adjacency[node], reverse=True)
                    if child not in visited
                )
    reverse: dict[str, set[str]] = {node: set() for node in adjacency}
    for node, targets in adjacency.items():
        for target in targets:
            reverse[target].add(node)
    visited.clear()
    result = []
    for root in reversed(finished):
        if root in visited:
            continue
        group: set[str] = set()
        pending = [root]
        visited.add(root)
        while pending:
            node = pending.pop()
            group.add(node)
            for parent in sorted(reverse[node]):
                if parent not in visited:
                    visited.add(parent)
                    pending.append(parent)
        result.append(tuple(sorted(group)))
    return tuple(sorted(result))
