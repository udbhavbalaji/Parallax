# Contributing

Use Python 3.10+, Clang, Node.js, and Go for the full test suite. Run `npm ci --ignore-scripts --no-audit --no-fund` once, then `python3 -m unittest discover -s tests -v` before submitting a change. Add fictional fixtures for parser behavior and keep every graph relationship tied to a source location. Do not add LLMs, telemetry, external services, repository build execution, or proprietary firmware.

Changes to parsing should include a focused fixture and a test. Update the coverage and limitation documentation when a relationship type is added or its meaning changes. Keep the target repository read-only; place indexes and generated reports elsewhere.
