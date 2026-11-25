"""Conservative, source-backed Python call extraction using the standard AST."""
from __future__ import annotations

import ast
from pathlib import Path


def parse_python(sources: list[Path], root: Path) -> dict[str, dict]:
    trees: dict[str, ast.Module] = {}
    facts: dict[str, dict] = {}
    definitions: dict[tuple[str, str], str] = {}
    functions: list[tuple[str, str, ast.FunctionDef | ast.AsyncFunctionDef, str | None]] = []

    def module_name(relative: str) -> str:
        parts = list(Path(relative).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        return ".".join(parts)

    for source in sources:
        relative = str(source.relative_to(root))
        data = source.read_bytes()
        facts[relative] = {"symbols": [], "calls": [], "diagnostics": "", "clang_exit": 0,
                           "source_size": len(data)}
        try:
            trees[relative] = ast.parse(data, filename=relative)
        except (SyntaxError, ValueError) as exc:
            facts[relative]["diagnostics"] = str(exc)
            facts[relative]["clang_exit"] = 1

    for relative, tree in trees.items():
        module = module_name(relative)

        def collect(body: list[ast.stmt], prefix: str = "", owner: str | None = None) -> None:
            for item in body:
                if isinstance(item, ast.ClassDef):
                    collect(item.body, prefix + item.name + ".", item.name)
                elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    qualified = prefix + item.name
                    identity = f"fn:python:{relative}:{qualified}"
                    name_at = item.lineno
                    facts[relative]["symbols"].append({"id": identity, "name": item.name,
                        "qualified_name": qualified, "language": "python", "file": relative,
                        "line": name_at, "column": item.col_offset + 1, "start_line": item.lineno,
                        "end_line": item.end_lineno or item.lineno, "module": module,
                        "type": "function", "linkage": "module"})
                    definitions[(module, qualified)] = identity
                    functions.append((relative, qualified, item, owner))
                    # Nested definitions are modeled separately, with their own call sites.
                    collect(item.body, qualified + ".", None)

        collect(tree.body)

    for relative, qualified, function, owner in functions:
        module = module_name(relative)
        tree = trees[relative]
        imports: dict[str, tuple[str, str | None]] = {}
        package = module if Path(relative).stem == "__init__" else module.rpartition(".")[0]
        for item in tree.body:
            if isinstance(item, ast.Import):
                for alias in item.names:
                    imports[alias.asname or alias.name.split(".")[0]] = (alias.name, None)
            elif isinstance(item, ast.ImportFrom):
                if item.level:
                    parts = package.split(".") if package else []
                    base = ".".join(parts[:max(0, len(parts) - item.level + 1)])
                    imported_module = ".".join(x for x in (base, item.module or "") if x)
                else:
                    imported_module = item.module or ""
                for alias in item.names:
                    imports[alias.asname or alias.name] = (imported_module, alias.name)

        # A local binding may shadow a module function. Treat such calls as unresolved.
        bound = {arg.arg for arg in (*function.args.posonlyargs, *function.args.args,
                                     *function.args.kwonlyargs)}
        if function.args.vararg:
            bound.add(function.args.vararg.arg)
        if function.args.kwarg:
            bound.add(function.args.kwarg.arg)
        class Binder(ast.NodeVisitor):
            def visit_Name(self, node: ast.Name) -> None:
                if isinstance(node.ctx, (ast.Store, ast.Del)):
                    bound.add(node.id)
            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                bound.add(node.name)
            visit_AsyncFunctionDef = visit_FunctionDef
            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                bound.add(node.name)
            def visit_Lambda(self, node: ast.Lambda) -> None:
                pass
        binder = Binder()
        for statement in function.body:
            binder.visit(statement)

        class Calls(ast.NodeVisitor):
            def visit_Call(self, node: ast.Call) -> None:
                target = None
                expression = node.func
                if isinstance(expression, ast.Name):
                    if expression.id not in bound:
                        imported = imports.get(expression.id)
                        if imported and imported[1]:
                            target = definitions.get((imported[0], imported[1]))
                        elif not imported:
                            parent = qualified.rpartition(".")[0]
                            target = (definitions.get((module, f"{parent}.{expression.id}")) if parent else None)
                            target = target or definitions.get((module, expression.id))
                    else:
                        # A nested function can be resolved by its lexical identity.
                        nested = f"{qualified}.{expression.id}"
                        target = definitions.get((module, nested))
                elif isinstance(expression, ast.Attribute) and isinstance(expression.value, ast.Name):
                    receiver = expression.value.id
                    imported = imports.get(receiver)
                    if imported and receiver not in bound:
                        imported_module = imported[0] if imported[1] is None else f"{imported[0]}.{imported[1]}"
                        target = definitions.get((imported_module, expression.attr))
                    elif receiver in {"self", "cls"} and owner:
                        target = definitions.get((module, f"{owner}.{expression.attr}"))
                try:
                    target_name = ast.unparse(expression)
                except ValueError:
                    target_name = None
                facts[relative]["calls"].append({"source": f"fn:python:{relative}:{qualified}",
                    "target": target, "target_name": target_name, "file": relative,
                    "line": node.lineno, "column": node.col_offset + 1, "type": "calls"})
                self.generic_visit(node)
            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                pass
            visit_AsyncFunctionDef = visit_FunctionDef
            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                pass
            def visit_Lambda(self, node: ast.Lambda) -> None:
                pass
        visitor = Calls()
        for statement in function.body:
            visitor.visit(statement)
    return facts
