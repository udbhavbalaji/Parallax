# Architecture

Language adapters in `cie/clang_ast.py`, `cie/python_ast.py`, `cie/ts_ast.cjs`, and `cie/go_ast.go` extract function definitions and call sites. `cie/index.py` stores common facts in SQLite. `cie/graph.py` resolves the adapters' symbol identities into typed, directed edges with evidence. `cie/report.py` embeds those facts into one offline HTML document. `cie/cli.py` is the current interface.

The graph's stable identity within a checkout is `fn:external:<name>` for external C functions, `fn:static:<relative-source-path>:<name>` for file-local C functions, and language-prefixed path and qualified-name identities for Python, TypeScript, and Go. Go identities also include the package clause to separate external test packages. External duplicate C definitions are reported as ambiguous. Call edges are directed caller → callee, with the source call location and a `verified` or `unresolved` resolution status. Dynamic or indirect calls remain unresolved. Source locations are relative to the analyzed root; report links are generated for local files.

Indexing reads `.c`, `.py`, `.ts`, `.tsx`, and `.go` files. C optionally reads `compile_commands.json`, accepts a small allowlist of parse flags, and invokes Clang directly. Python uses `ast`. TypeScript uses a pinned compiler API package with only local relative imports and root `tsconfig.json` path aliases. Go compiles and runs this project's standard-library-only parser helper. It never executes repository commands, build scripts, or plugins. The index and report must be outside the analyzed repository. C file signatures include source size and timestamp, in-tree header metadata, accepted flags, Clang command, and parser version. Other languages use group signatures so cross-file resolution changes invalidate the group. Parser source, TypeScript's root config and compiler package, and Go's module declaration contribute to these signatures.

The graph view starts at one function and expands on demand. It limits visible nodes and depth to avoid an accidental whole-repository view. The HTML embeds the full indexed metadata, which is suitable for the initial small/medium repository use case. A later local query protocol can avoid large report files.

## Coverage model

Parser diagnostics are retained per file. A graph edge is `verified` when its direct target has one indexed definition. Calls with no provable target, indirect calls, and duplicate external definitions are unresolved or ambiguous. This says nothing about runtime scheduling, preprocessor variants, Go build tags, dynamic dispatch, or whether a reachable caller's behavior is affected by a change.

## Design records

See [ADR 0001](docs/adr/0001-parser-and-viewer.md) and [ADR 0002](docs/adr/0002-language-adapters.md).
