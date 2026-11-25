"""Command-line entry point."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .graph import build_graph, select_symbol, traverse
from .index import default_index, index_repository, load_index
from .report import write_html


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cie", description="Offline C, Python, TypeScript, and Go function explorer")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root")
    parser.add_argument("--index", type=Path, help="SQLite index path, outside the repository")
    parser.add_argument("--compile-commands", type=Path, help="Existing compile_commands.json")
    parser.add_argument("--clang", default="clang", help="Clang executable")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("index", help="Index supported source files")
    explore = sub.add_parser("explore", help="Explore a function")
    selector = explore.add_mutually_exclusive_group(required=True)
    selector.add_argument("--symbol")
    selector.add_argument("--id")
    selector.add_argument("--file", help="Source path relative to root; use with --line")
    explore.add_argument("--line", type=int)
    explore.add_argument("--depth", type=int, default=1)
    explore.add_argument("--direction", choices=["both", "callers", "callees"], default="both")
    explore.add_argument("--max-nodes", type=int, default=80)
    explore.add_argument("--html", type=Path, help="Write self-contained interactive HTML outside root")
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve()
        index_path = (args.index or default_index(root)).resolve()
        if args.command == "index":
            result = index_repository(root, index_path, args.compile_commands, args.clang)
        else:
            if args.file and not args.line:
                raise ValueError("--file requires --line")
            graph = build_graph(load_index(index_path))
            node = select_symbol(graph, symbol=args.symbol, identity=args.id, file=args.file, line=args.line)
            result = traverse(graph, node["id"], args.depth, args.max_nodes, args.direction)
            if args.html:
                output = args.html.resolve()
                if output.is_relative_to(root):
                    raise ValueError("HTML report must be outside the analyzed repository")
                output.parent.mkdir(parents=True, exist_ok=True)
                write_html(graph, node["id"], root, output, args.max_nodes)
                result["html"] = str(output)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"cie: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
