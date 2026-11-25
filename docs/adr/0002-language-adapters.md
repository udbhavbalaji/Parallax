# ADR 0002: Conservative language adapters

Status: Accepted for initial multi-language support

Python uses the standard `ast` module, TypeScript uses the pinned Apache 2.0 TypeScript compiler API, and Go uses its standard `go/parser` and `go/ast` packages. Each adapter emits the same symbols and source-backed call facts as the C adapter. The shared graph and HTML viewer need no language-specific code.

The parsers run from this project's installation. TypeScript resolves only local imports and root `tsconfig.json` path aliases; it does not load repository plugins or dependency code. Go compiles only the checked-in helper with the local Go toolchain, with module download and workspace loading disabled. Python parses source text without importing it. The analyzed repository is never built or executed.

The first release favors sound, direct edges over broad guesses. Dynamic Python dispatch, TypeScript calls through external dependencies or unknown types, and Go interface and arbitrary value method calls remain unresolved with source evidence. Go build tags and generated code are not evaluated. Each language group's cache is invalidated when its source files change; relevant root configuration is included where used.

Future work may add safe type-aware resolution and package configuration without running target build commands. Those improvements should be measured against real repositories and retain explicit coverage reporting.
