"""Extract source-backed C facts from Clang's JSON AST."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess


class ClangError(RuntimeError):
    pass


def safe_compile_flags(entry: dict | None, source: Path) -> tuple[list[str], list[str]]:
    """Allow only parsing options; never pass compiler commands or plugin flags through."""
    if not entry:
        return ["-std=c11"], []
    import shlex

    args = entry.get("arguments") or shlex.split(entry.get("command", ""))
    args = list(args[1:]) if args else []
    allowed: list[str] = []
    skipped: list[str] = []
    directory = Path(entry.get("directory") or source.parent).resolve()
    path_options = {"-I", "-isystem", "-iquote", "-idirafter", "-isysroot"}
    value_options = {"-D", "-U", "-std", "-target"}
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "-o" and i + 1 < len(args):
            i += 2
            continue
        if arg == str(source) or (not arg.startswith("-") and (directory / arg).resolve() == source.resolve()):
            i += 1
            continue
        if arg in {"-c", "-fsyntax-only", "-g"} or arg.startswith(("-W", "-O")):
            i += 1
            continue
        if arg in path_options | value_options and i + 1 < len(args):
            value = args[i + 1]
            if arg in path_options and not Path(value).is_absolute():
                value = str((directory / value).resolve())
            allowed.extend([arg, value])
            i += 2
            continue
        if arg.startswith(("-I", "-D", "-U")) and len(arg) > 2:
            prefix, value = arg[:2], arg[2:]
            if prefix == "-I" and not Path(value).is_absolute():
                value = str((directory / value).resolve())
            allowed.append(prefix + value)
        elif arg.startswith("-std=") or arg.startswith("--target="):
            allowed.append(arg)
        elif arg == "-nostdinc":
            allowed.append(arg)
        else:
            skipped.append(arg)
        i += 1
    return allowed, skipped


def parse_source(source: Path, root: Path, clang: str, flags: list[str]) -> dict:
    command = [clang, "-x", "c", "-fsyntax-only", "-Xclang", "-ast-dump=json", *flags, str(source)]
    try:
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=45, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ClangError(f"Clang failed for {source}: {exc}") from exc
    try:
        ast = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ClangError(f"Clang produced no usable AST for {source}: {result.stderr[:1000]}") from exc
    source_bytes = source.read_bytes()
    lines = [0]
    for index, byte in enumerate(source_bytes):
        if byte == 10:
            lines.append(index + 1)

    def location(point: dict) -> dict | None:
        offset = point.get("offset")
        if offset is None or offset >= len(source_bytes):
            return None
        from bisect import bisect_right
        line = bisect_right(lines, offset)
        return {"file": str(source.relative_to(root)), "line": line, "column": offset - lines[line - 1] + 1, "offset": offset}

    def is_source_function(node: dict) -> bool:
        loc = node.get("loc", {})
        file = loc.get("file")
        if file and Path(file).resolve() != source:
            return False
        offset = loc.get("offset")
        name = node.get("name", "")
        return isinstance(offset, int) and source_bytes[offset:offset + len(name.encode())] == name.encode()

    definitions = []
    declarations = {}
    def walk_decls(node: dict):
        if node.get("kind") == "FunctionDecl" and is_source_function(node):
            name = node.get("name", "")
            declarations[node["id"]] = {"name": name, "static": node.get("storageClass") == "static"}
            body = next((child for child in node.get("inner", []) if child.get("kind") == "CompoundStmt"), None)
            if body:
                loc = location(node.get("loc", {}))
                begin = location(node.get("range", {}).get("begin", {}))
                end = location(body.get("range", {}).get("end", {}))
                if loc and begin and end:
                    definitions.append((node, body, loc, begin, end))
        for child in node.get("inner", []):
            walk_decls(child)
    walk_decls(ast)
    symbols = []
    calls = []
    relative = str(source.relative_to(root))
    for node, body, loc, begin, end in definitions:
        name = node["name"]
        static = node.get("storageClass") == "static"
        identity = f"fn:static:{relative}:{name}" if static else f"fn:external:{name}"
        symbols.append({"id": identity, "name": name, "file": relative, "line": loc["line"],
                        "column": loc["column"], "start_line": begin["line"], "end_line": end["line"],
                        "module": str(Path(relative).with_suffix("")), "type": "function", "linkage": "static" if static else "external"})

        def walk_calls(part: dict):
            if part.get("kind") == "CallExpr":
                refs = []
                def find_refs(item: dict):
                    if item.get("kind") == "DeclRefExpr" and item.get("referencedDecl"):
                        refs.append(item["referencedDecl"])
                    for child in item.get("inner", []):
                        find_refs(child)
                first = part.get("inner", [None])[0]
                if first:
                    find_refs(first)
                target = next((ref for ref in refs if ref.get("kind") == "FunctionDecl"), None)
                at = location(part.get("range", {}).get("begin", {}))
                if at:
                    target_name = target.get("name") if target else None
                    declaration = declarations.get(target.get("id")) if target else None
                    target_id = (f"fn:static:{relative}:{target_name}" if declaration and declaration["static"] else
                                 f"fn:external:{target_name}" if target_name else None)
                    calls.append({"source": identity, "target": target_id, "target_name": target_name,
                                  "file": relative, "line": at["line"], "column": at["column"],
                                  "type": "calls"})
            for child in part.get("inner", []):
                walk_calls(child)
        walk_calls(body)
    diagnostics = result.stderr.strip()
    return {"symbols": symbols, "calls": calls, "diagnostics": diagnostics,
            "clang_exit": result.returncode, "source_size": len(source_bytes)}
