# Code Impact Explorer

Code Impact Explorer (`cie`) is an offline, deterministic function call graph explorer for C, Python, TypeScript/TSX, and Go. It starts from one function and shows source-backed direct callers and callees. It never runs the analyzed repository's build scripts or writes to that repository.

## Requirements

- Python 3.10 or newer
- Clang with `-ast-dump=json` support for C (tested with Clang 23 on Linux; Apple Clang should be checked on macOS)
- Node.js and the pinned TypeScript compiler package for TypeScript/TSX
- Go toolchain for Go analysis
- Linux or macOS

Only install the tools for languages you analyze. Python analysis uses the Python standard library. TypeScript needs a one-time `npm ci --ignore-scripts` in this checkout; the compiler package must live outside the analyzed repository. No service, account, model, or runtime network access is required. After installation, the tool runs offline.

## Quick start

From this project directory:

```sh
python3 -m cie.cli --root fixtures/synthetic-bms --index /tmp/cie-fixture.sqlite3 index
python3 -m cie.cli --root fixtures/synthetic-bms --index /tmp/cie-fixture.sqlite3 explore --file src/monitor.c --line 14 --html /tmp/cie-monitor.html
```

Open `/tmp/cie-monitor.html` in a browser. Click a node to inspect its source and expand direct relationships. Click an edge for the call-site evidence. The report is a single file with no external requests. Its source links refer to local files on the machine that generated it.

For a personal repository (replace the source location with a function in that repository):

```sh
python3 -m cie.cli --root /path/to/repo index
python3 -m cie.cli --root /path/to/repo explore --symbol checkCellVoltage --depth 2 --html /tmp/check-cell.html
```

For TypeScript, install the pinned parser first in the Code Impact Explorer checkout:

```sh
npm ci --ignore-scripts --no-audit --no-fund
python3 -m cie.cli --root fixtures/synthetic-languages/typescript --index /tmp/cie-ts.sqlite3 index
python3 -m cie.cli --root fixtures/synthetic-languages/typescript --index /tmp/cie-ts.sqlite3 explore --file src/main.ts --line 4 --html /tmp/cie-ts.html
```

Python and Go use the same `index` and `explore` commands with `.py` or `.go` locations. For an installed Python wheel, set `CIE_TYPESCRIPT_MODULE` to an absolute path to a trusted TypeScript package installed outside the analyzed repository. The index and HTML report must also be outside that repository.

The default SQLite index lives under `~/.cache/code-impact-explorer`, outside the target repository. Provide `--index /path/outside/repo/index.sqlite3` to choose another location. `--symbol` requires a unique indexed name; use `--file` plus `--line`, or `--id`, to disambiguate static functions. The CLI prints structured JSON even when writing HTML.

For C, use `--compile-commands /path/to/compile_commands.json` to supply an existing compilation database. Cie reads only a restricted set of parsing flags: include paths, definitions, language standard, target, sysroot, and `-nostdinc`. It does not run the database's compiler command, build scripts, plugins, or response files. Unsupported flags are ignored. The index command reports Clang diagnostics; missing flags or headers can reduce coverage.

## Current scope

The index accepts `.c`, `.py`, `.ts`, `.tsx`, and `.go` files. It resolves direct calls when the parser can prove a target is an indexed function and labels other calls unresolved. Each call edge has an evidence file, line, and column. C distinguishes file-local `static` symbols. Python tracks top-level functions, class methods, imports, and lexical nested functions. TypeScript tracks function declarations, class methods, and function-valued variables with local import resolution. Go tracks package functions and receiver methods with conservative syntactic resolution. A SQLite cache invalidates C entries on source, header, or compiler-flag changes, and language groups on source or relevant configuration changes.

The graph uses a bounded, bottom-up view. Default depth is one, with caller/callee controls, click-to-expand, collapse, search, pan, zoom, module ordering, and source links. The HTML report embeds graph data and code locations. It does not embed source file contents.

Known limitations:

- Static call edges are potential dependencies, not runtime behavior. C function pointers, macros, global reads and writes, RTOS tasks, interrupts, and conditional-build variants are not inferred.
- Definitions in headers and external headers are not indexed as graph nodes. Header-only or macro-generated functions may be absent.
- Global external functions with conflicting definitions are marked ambiguous. Cie does not simulate linker decisions.
- Compilation database commands are sanitized, so unusual compiler configurations can produce incomplete ASTs. Clang diagnostics are exposed rather than silently treated as complete coverage.
- If a source has multiple compilation commands, the first configuration is indexed and a coverage warning is shown.
- Python dynamic imports, monkey-patching, and decorators are not resolved. Instance method calls are resolved only for `self` and `cls` within a known class.
- TypeScript uses local relative imports and path aliases from the root `tsconfig.json`. It does not load external packages or execute TypeScript config plugins; calls into dependencies and dynamic dispatch remain unresolved. TSX files are parsed, but JSX component tags are not treated as function calls.
- Go uses the standard parser without `go/types`; interface dispatch, most value method calls, build tags, and generated code are not modeled. Indexed files may include mutually exclusive build variants.
- The HTML report contains all indexed node and edge metadata for local expansion; very large repositories will need a lazy local data server in a later release.
- The Git impact analyzer and VS Code extension are planned phases, not part of this initial MVP.

Static reachability means a possible dependency path, not proof that a runtime behavior will occur or change.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

The synthetic C firmware fixture is fictional and **not production-safe BMS firmware**. Additional Python, TypeScript, and Go fixtures exercise cross-file calls, methods, recursion, and unresolved targets.

## Privacy and licensing

The application performs local analysis only. It has no telemetry, LLM dependency, cloud backend, authentication, or runtime network request. Reports do not fetch external resources. The project is MIT licensed. The TypeScript compiler package is Apache 2.0 licensed; LLVM is Apache 2.0 with LLVM exceptions ([LLVM licensing](https://llvm.org/docs/DeveloperPolicy.html#license)). Python and Go standard-library parsers are used for those languages. The trusted TypeScript and Go parser tools run from this project's installation, never from an analyzed repository.

See [Architecture](ARCHITECTURE.md), [Roadmap](ROADMAP.md), and [Contributing](CONTRIBUTING.md).
