from pathlib import Path
import shutil
import tempfile
import unittest

from cie.graph import build_graph, select_symbol, traverse
from cie.index import index_repository, load_index


ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic-languages"
PACKAGE = Path(__file__).resolve().parents[1] / "node_modules" / "typescript"


class LanguageTests(unittest.TestCase):
    def test_unsupported_repository_reports_zero_coverage(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as output_dir:
            (Path(source_dir) / "main.js").write_text("function run() {}\n")
            report = index_repository(Path(source_dir), Path(output_dir) / "index.sqlite3")
            self.assertEqual(report["files"], 0)
            self.assertIn("No supported", report["coverage_warnings"][0]["message"])

    def examine(self, language):
        fixture = ROOT / language
        with tempfile.TemporaryDirectory() as directory:
            index = Path(directory) / "index.sqlite3"
            report = index_repository(fixture, index)
            self.assertEqual(report["diagnostics"], [])
            self.assertEqual(report["indexed"], report["files"])
            graph = build_graph(load_index(index))
            cached = index_repository(fixture, index)
            self.assertEqual(cached["cached"], cached["files"])
            return graph

    def assert_edge(self, graph, source, target, file):
        match = [edge for edge in graph["edges"] if edge["source"] == source and edge["target"] == target]
        self.assertEqual(len(match), 1)
        self.assertEqual(match[0]["resolution"], "verified")
        self.assertEqual(match[0]["evidence"]["file"], file)
        self.assertGreater(match[0]["evidence"]["line"], 0)

    def test_python_imports_methods_recursion_and_unresolved(self):
        graph = self.examine("python")
        core = "fn:python:pkg/core.py:"
        entry = "fn:python:pkg/entry.py:run"
        self.assert_edge(graph, entry, core + "check", "pkg/entry.py")
        self.assert_edge(graph, entry, core + "helper", "pkg/entry.py")
        self.assert_edge(graph, core + "Worker.run", core + "Worker.finish", "pkg/core.py")
        self.assert_edge(graph, core + "recurse", core + "recurse", "pkg/core.py")
        self.assertTrue(any(e["resolution"] == "unresolved" and e["source"] == core + "unknown"
                            for e in graph["edges"]))
        self.assertTrue(any(e["resolution"] == "unresolved" and e["source"] == core + "shadow"
                            for e in graph["edges"]))
        node = select_symbol(graph, file="pkg/entry.py", line=6)
        self.assertEqual(node["id"], entry)
        self.assertIn(core + "check", {n["id"] for n in traverse(graph, entry)["nodes"]})

    @unittest.skipUnless(shutil.which("node") and PACKAGE.exists(), "TypeScript compiler not installed")
    def test_typescript_imports_methods_recursion_and_unresolved(self):
        graph = self.examine("typescript")
        util = "fn:typescript:src/util.ts:"
        main = "fn:typescript:src/main.ts:"
        self.assert_edge(graph, main + "run", util + "check", "src/main.ts")
        self.assert_edge(graph, main + "run", util + "wrap", "src/main.ts")
        self.assert_edge(graph, main + "Worker.run", main + "Worker.finish", "src/main.ts")
        self.assert_edge(graph, util + "recurse", util + "recurse", "src/util.ts")
        self.assert_edge(graph, "fn:typescript:src/alias.ts:aliasRun", util + "check", "src/alias.ts")
        self.assertEqual(select_symbol(graph, file="src/widget.tsx", line=2)["name"], "Widget")
        self.assertTrue(any(e["resolution"] == "unresolved" and e["source"] == main + "unknown"
                            for e in graph["edges"]))
        self.assertTrue(any(e["resolution"] == "unresolved" and e["source"] == main + "shadow"
                            for e in graph["edges"]))

    @unittest.skipUnless(shutil.which("go"), "Go toolchain not installed")
    def test_go_imports_methods_recursion_and_unresolved(self):
        graph = self.examine("go")
        pkg = "fn:go:pkg:pkg:"
        self.assert_edge(graph, "fn:go:.:synthetic:Run", pkg + "Check", "main.go")
        self.assert_edge(graph, pkg + "Check", pkg + "helper", "pkg/check.go")
        self.assert_edge(graph, pkg + "Worker.Run", pkg + "Worker.Finish", "pkg/check.go")
        self.assert_edge(graph, pkg + "Recurse", pkg + "Recurse", "pkg/check.go")
        self.assertTrue(any(e["resolution"] == "unresolved" and e["source"] == pkg + "Unknown"
                            for e in graph["edges"]))
        self.assertTrue(any(e["resolution"] == "unresolved" and e["source"] == pkg + "shadow"
                            for e in graph["edges"]))
        self.assert_edge(graph, "fn:go:pkg:pkg_test:Exercise", "fn:go:pkg:pkg_test:Check", "pkg/check_test.go")


if __name__ == "__main__":
    unittest.main()
