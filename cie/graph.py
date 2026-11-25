"""Resolve and traverse the typed, evidence-backed call graph."""
from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path


def build_graph(facts: dict) -> dict:
    definitions = defaultdict(list)
    for symbol in facts["symbols"]:
        definitions[symbol["id"]].append(symbol)
    nodes = {}
    for identity, occurrences in definitions.items():
        primary = occurrences[0].copy()
        primary["resolution"] = "verified" if len(occurrences) == 1 else "ambiguous"
        primary["definitions"] = [{"file": x["file"], "line": x["line"]} for x in occurrences]
        nodes[identity] = primary
    edges = []
    for count, call in enumerate(facts["calls"]):
        target = call["target"]
        if not target:
            target = f"unresolved:{call['file']}:{call['line']}:{call['column']}:{count}"
            label = call.get("target_name") or "Indirect call"
            nodes[target] = {"id": target, "name": f"Unresolved: {label}", "file": call["file"],
                             "line": call["line"], "column": call["column"], "module": str(Path(call["file"]).with_suffix("")),
                             "type": "unresolved", "resolution": "unresolved"}
        elif target not in nodes:
            nodes[target] = {"id": target, "name": call["target_name"], "file": None,
                             "line": None, "column": None, "module": None, "type": "external_declaration",
                             "resolution": "unresolved"}
        resolution = nodes[target]["resolution"]
        edges.append({"id": f"call:{count}", "type": "calls", "source": call["source"],
                      "target": target, "evidence": {"file": call["file"], "line": call["line"],
                                                     "column": call["column"]}, "resolution": resolution,
                      "certainty": "static_direct" if resolution == "verified" else "unresolved"})
    return {"nodes": list(nodes.values()), "edges": edges, "diagnostics": facts.get("diagnostics", []),
            "coverage_warnings": facts.get("coverage_warnings", [])}


def select_symbol(graph: dict, symbol: str | None = None, identity: str | None = None,
                  file: str | None = None, line: int | None = None) -> dict:
    nodes = [n for n in graph["nodes"] if n["type"] == "function"]
    if identity:
        matching = [n for n in nodes if n["id"] == identity]
    elif file and line:
        matching = [n for n in nodes if n["file"] == file and n["start_line"] <= line <= n["end_line"]]
        matching.sort(key=lambda n: n["end_line"] - n["start_line"])
        matching = matching[:1]
    elif symbol:
        matching = [n for n in nodes if n["name"] == symbol]
    else:
        raise ValueError("Specify a symbol name, identity, or source location")
    if len(matching) != 1:
        options = [n["id"] for n in matching]
        raise ValueError(f"Expected one symbol; found {len(matching)}. Candidates: {options}")
    return matching[0]


def traverse(graph: dict, center: str, depth: int = 1, max_nodes: int = 80,
             direction: str = "both") -> dict:
    if depth < 0 or max_nodes < 1:
        raise ValueError("Depth must be nonnegative and max nodes positive")
    nodes = {n["id"]: n for n in graph["nodes"]}
    if center not in nodes:
        raise ValueError(f"Unknown node: {center}")
    adjacency = defaultdict(list)
    for edge in graph["edges"]:
        if direction in {"both", "callees"}:
            adjacency[edge["source"]].append((edge["target"], edge))
        if direction in {"both", "callers"}:
            adjacency[edge["target"]].append((edge["source"], edge))
    visited = {center}
    queue = deque([(center, 0)])
    while queue:
        current, level = queue.popleft()
        if level >= depth:
            continue
        for neighbor, _ in adjacency[current]:
            if neighbor not in visited and len(visited) < max_nodes:
                visited.add(neighbor)
                queue.append((neighbor, level + 1))
    return {"center": center, "nodes": [nodes[x] for x in sorted(visited)],
            "edges": [e for e in graph["edges"] if e["source"] in visited and e["target"] in visited],
            "truncated": len(visited) >= max_nodes, "depth": depth,
            "diagnostics": graph.get("diagnostics", []),
            "coverage_warnings": graph.get("coverage_warnings", [])}
