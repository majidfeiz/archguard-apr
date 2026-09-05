"""Conservative AST extraction; never import or evaluate target code."""

import ast

from archguard.domain.repository import (
    ImportKind,
    ImportSnapshot,
    MethodKind,
    SymbolKind,
    SymbolSnapshot,
    symbol_id,
    visibility,
)


def callable_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Call):
        return callable_name(node.func)
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = (
            callable_name(node.value) if isinstance(node.value, (ast.Name, ast.Attribute)) else None
        )
        return f"{parent}.{node.attr}" if parent else None
    return None


class Extractor(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.parents: list[tuple[str, SymbolKind]] = []
        self.symbols: list[SymbolSnapshot] = []
        self.imports: list[ImportSnapshot] = []
        self.type_checking = False

    def visit_If(self, node: ast.If) -> None:
        previous = self.type_checking
        test = (
            callable_name(node.test) if isinstance(node.test, (ast.Name, ast.Attribute)) else None
        )
        self.type_checking = previous or test in {"TYPE_CHECKING", "typing.TYPE_CHECKING"}
        for child in node.body:
            self.visit(child)
        self.type_checking = previous
        for child in node.orelse:
            self.visit(child)

    def symbol(
        self, node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef, kind: SymbolKind
    ) -> None:
        parent = ".".join(name for name, _ in self.parents) or None
        qualified = f"{parent}.{node.name}" if parent else node.name
        decorators = tuple(
            name for d in node.decorator_list if (name := callable_name(d)) is not None
        )
        method = MethodKind.NOT_APPLICABLE
        if kind != SymbolKind.CLASS and self.parents and self.parents[-1][1] == SymbolKind.CLASS:
            method = MethodKind.INSTANCE
            for decorator, classification in [
                ("staticmethod", MethodKind.STATIC),
                ("classmethod", MethodKind.CLASS),
                ("property", MethodKind.PROPERTY),
            ]:
                if decorator in decorators:
                    method = classification
                    break
        self.symbols.append(
            SymbolSnapshot(
                symbol_id(self.path, qualified, node.lineno, node.col_offset),
                qualified,
                kind,
                self.path,
                node.lineno,
                node.end_lineno or node.lineno,
                node.col_offset,
                parent,
                visibility(node.name),
                decorators,
                method,
            )
        )
        self.parents.append((node.name, kind))
        for child in node.body:
            self.visit(child)
        self.parents.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.symbol(node, SymbolKind.CLASS)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.symbol(node, SymbolKind.FUNCTION)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.symbol(node, SymbolKind.ASYNC_FUNCTION)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(
                ImportSnapshot(
                    self.path,
                    node.lineno,
                    node.col_offset,
                    ImportKind.IMPORT,
                    alias.name,
                    None,
                    alias.asname,
                    0,
                    alias.name,
                    False,
                    self.type_checking,
                )
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        for alias in node.names:
            target = "." * node.level + module + ("." if module else "") + alias.name
            self.imports.append(
                ImportSnapshot(
                    self.path,
                    node.lineno,
                    node.col_offset,
                    ImportKind.FROM,
                    module,
                    alias.name,
                    alias.asname,
                    node.level,
                    target,
                    alias.name == "*",
                    self.type_checking,
                )
            )


def parse_source(
    text: str, path: str
) -> tuple[tuple[ImportSnapshot, ...], tuple[SymbolSnapshot, ...]]:
    tree = ast.parse(text, filename="<source>", feature_version=(3, 12))
    visitor = Extractor(path)
    visitor.visit(tree)
    return (
        tuple(sorted(visitor.imports, key=lambda i: (i.line, i.column, i.target, i.alias or ""))),
        tuple(sorted(visitor.symbols, key=lambda s: (s.start_line, s.column, s.identifier))),
    )
