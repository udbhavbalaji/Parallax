"""Persistent local index of Clang facts. The target tree is never written."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
from contextlib import closing
import subprocess
import tempfile

from .clang_ast import parse_source, safe_compile_flags
from .python_ast import parse_python


INDEX_SCHEMA_VERSION = 5
LANGUAGES = {".c": "c", ".py": "python", ".go": "go", ".ts": "typescript", ".tsx": "typescript"}
EXCLUDED_DIRS = {"node_modules", ".venv", "venv", "__pycache__", "dist", "build"}
ANALYSIS_NOTES = {
    "python": "Python dynamic calls, decorators, and monkey-patching are not resolved",
    "typescript": "TypeScript resolves local imports and root tsconfig paths; external packages and dynamic calls remain unresolved",
    "go": "Go interface dispatch and methods on arbitrary values are unresolved; build tags and generated code are not evaluated",
}


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
        if not path.resolve().is_relative_to(root):
            continue
        stat = path.stat()
        sha.update(f"{path.relative_to(root)}:{stat.st_size}:{stat.st_mtime_ns}".encode())
    return sha.hexdigest()


def _source_files(root: Path) -> dict[str, list[Path]]:
    sources: dict[str, list[Path]] = {language: [] for language in set(LANGUAGES.values())}
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in LANGUAGES:
            continue
        if not path.resolve().is_relative_to(root):
            continue
        if any(part.startswith(".") or part in EXCLUDED_DIRS for part in path.relative_to(root).parts[:-1]):
            continue
        sources[LANGUAGES[path.suffix]].append(path)
    for items in sources.values():
        items.sort()
    return sources


def _group_signature(sources: list[Path], root: Path, extra: str = "") -> str:
    details = [(str(path.relative_to(root)), path.stat().st_size, path.stat().st_mtime_ns) for path in sources]
    return hashlib.sha256(json.dumps([INDEX_SCHEMA_VERSION, details, extra]).encode()).hexdigest()


def _run_adapter(command: list[str], payload: dict, root: Path, language: str, env: dict | None = None) -> dict:
    try:
        process = subprocess.run(command, input=json.dumps(payload), capture_output=True, text=True,
                                 timeout=120, cwd=Path(__file__).resolve().parent.parent, env=env, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"{language} parser unavailable: {exc}") from exc
    if process.returncode:
        raise RuntimeError(f"{language} parser failed: {process.stderr[:1000]}")
    try:
        return json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{language} parser returned invalid facts: {process.stderr[:1000]}") from exc


def _go_module(root: Path) -> str:
    manifest = root / "go.mod"
    if not manifest.is_file():
        return ""
    for line in manifest.read_text(errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith("module "):
            return stripped[7:].strip().strip('"')
    return ""


def _parse_group(language: str, sources: list[Path], root: Path) -> dict[str, dict]:
    if language == "python":
        return parse_python(sources, root)
    relative = [str(path.relative_to(root)) for path in sources]
    if language == "typescript":
        env = os.environ.copy()
        env.pop("NODE_OPTIONS", None)
        env.pop("NODE_PATH", None)
        module = Path(os.environ.get("CIE_TYPESCRIPT_MODULE", str(Path(__file__).resolve().parent.parent /
                                                               "node_modules" / "typescript"))).resolve()
        if module.is_relative_to(root):
            raise ValueError("TypeScript compiler package must be outside the analyzed repository")
        if not module.is_dir():
            raise RuntimeError("TypeScript compiler package not found; run 'npm ci' in the CIE checkout "
                               "or set CIE_TYPESCRIPT_MODULE to a trusted installation outside the analyzed repository")
        return _run_adapter(["node", str(Path(__file__).with_name("ts_ast.cjs")), str(root), str(module)],
                            relative, root, language, env)
    if language == "go":
        env = os.environ.copy()
        env.update({"GO111MODULE": "off", "GOWORK": "off", "GOPROXY": "off",
                    "GOTOOLCHAIN": "local", "GOFLAGS": "",
                    "GOCACHE": str(Path(tempfile.gettempdir()) / "cie-go-cache")})
        return _run_adapter(["go", "run", str(Path(__file__).with_name("go_ast.go"))],
                            {"root": str(root), "files": relative, "module": _go_module(root)},
                            root, language, env)
    raise ValueError(f"Unsupported language: {language}")


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
    groups = _source_files(root)
    sources = groups["c"]
    counts = {language: len(items) for language, items in groups.items()}
    report = {"indexed": 0, "cached": 0, "files": sum(counts.values()), "languages": counts,
              "diagnostics": [], "coverage_warnings": [],
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
        for language in ("python", "typescript", "go"):
            language_sources = groups[language]
            if not language_sources:
                continue
            report["coverage_warnings"].append({"file": None, "message": ANALYSIS_NOTES[language]})
            extra = _go_module(root) if language == "go" else ""
            if language == "typescript" and (root / "tsconfig.json").is_file():
                extra = hashlib.sha256((root / "tsconfig.json").read_bytes()).hexdigest()
            signature = _group_signature(language_sources, root, extra)
            paths = {str(path.relative_to(root)) for path in language_sources}
            active.update(paths)
            if all(known.get(path) == signature for path in paths):
                report["cached"] += len(paths)
                continue
            parsed = _parse_group(language, language_sources, root)
            for relative in sorted(paths):
                facts = parsed.get(relative)
                if facts is None:
                    raise RuntimeError(f"{language} parser omitted {relative}")
                facts["language"] = language
                db.execute("INSERT OR REPLACE INTO files VALUES (?, ?, ?)", (relative, signature, json.dumps(facts)))
                report["indexed"] += 1
                if facts["diagnostics"] or facts["clang_exit"]:
                    report["diagnostics"].append({"file": relative, "clang_exit": facts["clang_exit"],
                                                  "message": facts["diagnostics"][:1000]})
        for obsolete in known.keys() - active:
            db.execute("DELETE FROM files WHERE path = ?", (obsolete,))
    if report["files"] == 0:
        report["coverage_warnings"].append({"file": None, "message": "No supported C, Python, Go, or TypeScript source files found"})
    return report


def load_index(index_path: Path) -> dict:
    if not index_path.exists():
        raise ValueError(f"No index at {index_path}; run 'cie index' first")
    symbols, calls, diagnostics, coverage_warnings = [], [], [], []
    languages = set()
    with closing(_db(index_path)) as db:
        for path, data in db.execute("SELECT path, facts FROM files ORDER BY path"):
            facts = json.loads(data)
            if facts.get("language") in ANALYSIS_NOTES:
                languages.add(facts["language"])
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
    coverage_warnings.extend({"file": None, "message": ANALYSIS_NOTES[language]} for language in sorted(languages))
    return {"symbols": symbols, "calls": calls, "diagnostics": diagnostics,
            "coverage_warnings": coverage_warnings}
