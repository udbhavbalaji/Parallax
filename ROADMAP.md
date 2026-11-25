# Roadmap

## Phase 1 — complete for MVP

Clang AST extraction, direct calls, static identity, cross-file resolution, persistent SQLite cache, CLI JSON output, and synthetic fixture tests.

## Phase 2 — complete for MVP

Self-contained offline HTML with bounded direct graph, click expansion and collapse, filters, search, pan and zoom, module ordering, source navigation, and evidence details.

## Phase 3 — next

VS Code extension: select a function by cursor location, open the shared graph in a webview, navigate to source, and query the local engine incrementally.

## Phase 4 — next

Git diff analyzer: compare base and head, map changed lines and added/deleted symbols using revision-specific indexes, handle renames, and label potential callers and propagation paths. Export local HTML.

## Phase 5 — research

Add reliable global read/write edges, then evaluate constrained function-pointer resolution, RTOS entry points, interrupt annotations, and firmware-specific relationships. Do not infer unsupported runtime paths.

## Scale work

Measure large C projects; add cancellable indexing, external-header invalidation, and lazy graph queries before changing the architecture.
