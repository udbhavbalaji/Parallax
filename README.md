# Code Impact Explorer

Code Impact Explorer (`cie`) is an offline, deterministic C function call graph explorer. It starts from one function and shows source-backed direct callers and callees. It never runs the analyzed repository's build scripts or writes to that repository.

## Requirements

- Python 3.10 or newer
- Clang with `-ast-dump=json` support (tested with Clang 23 on Linux; Apple Clang should be checked on macOS)
- Linux or macOS

No Python runtime packages, services, accounts, models, or network access are required. Clang is an external local executable. Install Clang and Python through the system's normal package manager. After installation, the tool runs offline.

## Quick start

From this project directory:

```sh
python3 -m cie.cli --root fixtures/synthetic-bms --index /tmp/cie-fixture.sqlite3 index
python3 -m cie.cli --root fixtures/synthetic-bms --index /tmp/cie-fixture.sqlite3 explore --file src/monitor.c --line 14 --html /tmp/cie-monitor.html
```

Open `/tmp/cie-monitor.html` in a browser. Click a node to inspect its source and expand direct relationships. Click an edge for the call-site evidence. The report is a single file with no external requests. Its source links refer to local files on the machine that generated it.

For a personal repository:

```sh
python3 -m cie.cli --root /path/to/repo index
python3 -m cie.cli --root /path/to/repo explore --symbol checkCellVoltage --depth 2 --html /tmp/check-cell.html
```

The default SQLite index lives under `~/.cache/code-impact-explorer`, outside the target repository. Provide `--index /path/outside/repo/index.sqlite3` to choose another location. `--symbol` requires a unique indexed name; use `--file` plus `--line`, or `--id`, to disambiguate static functions. The CLI prints structured JSON even when writing HTML.

Use `--compile-commands /path/to/compile_commands.json` to supply an existing compilation database. Cie reads only a restricted set of parsing flags: include paths, definitions, language standard, target, sysroot, and `-nostdinc`. It does not run the database's compiler command, build scripts, plugins, or response files. Unsupported flags are ignored. The index command reports Clang diagnostics; missing flags or headers can reduce coverage.

## Current scope

The MVP indexes `.c` files, resolves direct calls to indexed function definitions, distinguishes file-local `static` symbols, and labels calls to missing definitions or indirect targets as unresolved. Each call edge has an evidence file, line, and column. It caches per-source AST facts in SQLite and invalidates entries when source, in-tree headers, or accepted compiler flags change.

The graph uses a bounded, bottom-up view. Default depth is one, with caller/callee controls, click-to-expand, collapse, search, pan, zoom, module ordering, and source links. The HTML report embeds graph data and code locations. It does not embed source file contents.

Known limitations:

- Only C direct function calls are resolved. Function pointers, macros, global reads and writes, RTOS tasks, interrupts, and conditional-build variants are not inferred.
- Definitions in headers and external headers are not indexed as graph nodes. Header-only or macro-generated functions may be absent.
- Global external functions with conflicting definitions are marked ambiguous. Cie does not simulate linker decisions.
- Compilation database commands are sanitized, so unusual compiler configurations can produce incomplete ASTs. Clang diagnostics are exposed rather than silently treated as complete coverage.
- If a source has multiple compilation commands, the first configuration is indexed and a coverage warning is shown.
- The HTML report contains all indexed node and edge metadata for local expansion; very large repositories will need a lazy local data server in a later release.
- The Git impact analyzer and VS Code extension are planned phases, not part of this initial MVP.

Static reachability means a possible dependency path, not proof that a runtime behavior will occur or change.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

The synthetic fixture is fictional and **not production-safe BMS firmware**.

## Privacy and licensing

The application performs local analysis only. It has no telemetry, LLM dependency, cloud backend, authentication, or runtime network request. Reports do not fetch external resources. The project is MIT licensed. Python standard library and the user-installed Clang executable are the only runtime dependencies; LLVM is distributed under Apache 2.0 with LLVM exceptions ([LLVM licensing](https://llvm.org/docs/DeveloperPolicy.html#license)).

See [Architecture](ARCHITECTURE.md), [Roadmap](ROADMAP.md), and [Contributing](CONTRIBUTING.md).
