# Architecture

`cie/clang_ast.py` invokes a local Clang parser in syntax-only mode and extracts function definitions and direct call sites from its JSON AST. `cie/index.py` stores per-source facts in SQLite. `cie/graph.py` resolves names and file-local identities into typed, directed edges with evidence. `cie/report.py` embeds those facts into one offline HTML document. `cie/cli.py` is the current interface.

The graph's stable identity within a checkout is `fn:external:<name>` for external C functions and `fn:static:<relative-source-path>:<name>` for file-local functions. External duplicate definitions are reported as ambiguous. For the MVP, a module is a source file path without its `.c` suffix. Call edges are directed caller → callee, with the source call location and a `verified` or `unresolved` resolution status. Indirect calls remain unresolved. Source locations are relative to the analyzed root; report links are generated for local files.

Indexing reads `.c` files and optional `compile_commands.json`. It accepts a small allowlist of parse flags and invokes Clang directly; it never executes repository commands. The index and report must be outside the analyzed repository. Per-file signatures include source size and timestamp, in-tree header metadata, accepted flags, and Clang command. Header changes invalidate the affected cache conservatively by invalidating all source entries.

The graph view starts at one function and expands on demand. It limits visible nodes and depth to avoid an accidental whole-repository view. The HTML embeds the full indexed metadata, which is suitable for the initial small/medium repository use case. A later local query protocol can avoid large report files.

## Coverage model

Clang diagnostics are retained per file. A graph edge is `verified` when its direct target has one indexed definition. Calls with no indexed definition, indirect calls, and duplicate external definitions are unresolved or ambiguous. This says nothing about runtime scheduling, preprocessor variants, or whether a reachable caller's behavior is affected by a change.

## Design records

See [ADR 0001](docs/adr/0001-parser-and-viewer.md).
