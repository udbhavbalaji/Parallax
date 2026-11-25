# ADR 0001: Clang JSON AST and bundled SVG viewer

Status: Accepted for initial MVP

## Parser decision

We chose Clang's JSON AST through a syntax-only subprocess. It provides semantic declaration references and source ranges without binding to a particular Python libclang binary. It is available on macOS and Linux with standard Clang installations. Per-file facts can be cached in SQLite. The process boundary permits a strict compiler-flag allowlist and timeout.

libclang is a good future alternative for cursor APIs and USRs, but installing compatible Python bindings and native libraries across Apple Clang and Linux LLVM versions is more fragile. A native Clang tooling executable offers deeper control and incremental features at the cost of a C++ build toolchain. clangd's index is attractive for larger repositories and cross-translation-unit resolution, but its index format and daemon lifecycle add operational complexity to this local MVP.

This choice has limits: AST JSON is not a stable public interchange contract, each changed translation unit is parsed anew, and source identity for macro-generated code is incomplete. We pin behavior through integration tests and expose diagnostics.

References: [Clang AST introduction](https://clang.llvm.org/docs/IntroductionToTheClangAST.html), [JSON compilation database specification](https://clang.llvm.org/docs/JSONCompilationDatabase.html), and [Clang JSON AST dumper source](https://clang.llvm.org/doxygen/JSONNodeDumper_8h_source.html).

## Viewer decision

We chose a small bundled SVG/JavaScript viewer because its bounded graph needs no package download, build system, or external resource. It supports pan, zoom, search, relationship filtering, click expansion, collapse, and evidence inspection.

Cytoscape.js is the leading candidate for a later larger graph viewer because it has mature interactive graph layouts and selectors; bundling it would add size and a JavaScript dependency. React Flow offers polished node editing but adds React and focuses more on flow editing than dependency exploration. Graphviz produces excellent static layouts but needs an external binary and does not provide the desired incremental interaction by itself.

Revisit the viewer when measured repository sizes exceed the embedded-data approach.
