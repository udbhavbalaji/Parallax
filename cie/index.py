"""Persistent local index of Clang facts. The target tree is never written."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
from contextlib import closing

from .clang_ast import parse_source, safe_compile_flags


INDEX_SCHEMA_VERSION = 2


def default_index(root: Path) -> Path:
    digest = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]
    return Path.home() / ".cache" / "code-impact-explorer" / f"{digest}.sqlite3"


def _db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, signature TEXT NOT NULL, facts TEXT NOT NULL)")
    return db


def _compilation_database(path: Path | None) -> dict[str, dict]:
    if not path or not path.exists():
        return {}
    path = path.resolve()
    entries = json.loads(path.read_text())
    mapped = {}
    for entry in entries:
        entry = entry.copy()
        directory = Path(entry["directory"])
        if not directory.is_absolute():
            directory = path.parent / directory
        entry["directory"] = str(directory.resolve())
        source = Path(entry["file"])
        if not source.is_absolute():
            source = directory / source
        key = str(source.resolve())
        if key in mapped:
            mapped[key]["_multiple_commands"] = True
        else:
            mapped[key] = entry
    return mapped


def _header_signature(root: Path) -> str:
    sha = hashlib.sha256()
    for path in sorted(root.rglob("*.h")):
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        stat = path.stat()
        sha.update(f"{path.relative_to(root)}:{stat.st_size}:{stat.st_mtime_ns}".encode())
    return sha.hexdigest()


def index_repository(root: Path, index_path: Path | None = None,
                     compile_commands: Path | None = None, clang: str = "clang") -> dict:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"Repository does not exist: {root}")
    index_path = (index_path or default_index(root)).resolve()
    if index_path.is_relative_to(root):
        raise ValueError("Index must be outside the analyzed repository")
    database = _compilation_database(compile_commands or root / "compile_commands.json")
    headers = _header_signature(root)
    sources = sorted(p for p in root.rglob("*.c") if not any(part.startswith(".") for part in p.relative_to(root).parts))
    report = {"indexed": 0, "cached": 0, "files": len(sources), "diagnostics": [], "coverage_warnings": [],
              "compilation_database": bool(database), "index": str(index_path)}
    with closing(_db(index_path)) as db, db:
        known = {row[0]: row[1] for row in db.execute("SELECT path, signature FROM files")}
        active = set()
        for source in sources:
            relative = str(source.relative_to(root))
            active.add(relative)
            entry = database.get(str(source))
            flags, skipped = safe_compile_flags(entry, source)
            if not entry:
                report["coverage_warnings"].append({"file": relative, "message": "No compilation command; using -std=c11 only"})
            if skipped:
                report["coverage_warnings"].append({"file": relative, "message": f"Ignored compiler arguments: {skipped}"})
            if entry and entry.get("_multiple_commands"):
                report["coverage_warnings"].append({"file": relative, "message": "Multiple compilation commands; indexed first configuration only"})
            stat = source.stat()
            signature = hashlib.sha256(json.dumps([INDEX_SCHEMA_VERSION, stat.st_size, stat.st_mtime_ns, headers, flags, clang,
                                                   bool(entry and entry.get("_multiple_commands"))]).encode()).hexdigest()
            if known.get(relative) == signature:
                report["cached"] += 1
                continue
            facts = parse_source(source, root, clang, flags)
            if not entry:
                facts["no_compilation_command"] = True
            if skipped:
                facts["skipped_flags"] = skipped
            if entry and entry.get("_multiple_commands"):
                facts["multiple_commands"] = True
            db.execute("INSERT OR REPLACE INTO files VALUES (?, ?, ?)", (relative, signature, json.dumps(facts)))
            report["indexed"] += 1
            if facts["diagnostics"] or facts["clang_exit"]:
                report["diagnostics"].append({"file": relative, "clang_exit": facts["clang_exit"],
                                              "message": facts["diagnostics"][:1000]})
        for obsolete in known.keys() - active:
            db.execute("DELETE FROM files WHERE path = ?", (obsolete,))
    return report


def load_index(index_path: Path) -> dict:
    if not index_path.exists():
        raise ValueError(f"No index at {index_path}; run 'cie index' first")
    symbols, calls, diagnostics, coverage_warnings = [], [], [], []
    with closing(_db(index_path)) as db:
        for path, data in db.execute("SELECT path, facts FROM files ORDER BY path"):
            facts = json.loads(data)
            symbols.extend(facts["symbols"])
            calls.extend(facts["calls"])
            if facts.get("no_compilation_command"):
                coverage_warnings.append({"file": path, "message": "No compilation command; used -std=c11 only"})
            if facts.get("skipped_flags"):
                coverage_warnings.append({"file": path, "message": f"Ignored compiler arguments: {facts['skipped_flags']}"})
            if facts.get("multiple_commands"):
                coverage_warnings.append({"file": path, "message": "Multiple compilation commands; indexed first configuration only"})
            if facts["clang_exit"] or facts["diagnostics"]:
                diagnostics.append({"file": path, "clang_exit": facts["clang_exit"],
                                    "message": facts["diagnostics"][:1000]})
    return {"symbols": symbols, "calls": calls, "diagnostics": diagnostics,
            "coverage_warnings": coverage_warnings}
