import json
from pathlib import Path
import tempfile
import unittest

from cie.clang_ast import safe_compile_flags
from cie.graph import build_graph, select_symbol, traverse
from cie.index import index_repository, load_index
from cie.report import write_html


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic-bms"


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.index = Path(cls.tmp.name) / "fixture.sqlite3"
        cls.report = index_repository(FIXTURE, cls.index)
        cls.graph = build_graph(load_index(cls.index))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_symbols_and_cross_file_calls(self):
        self.assertEqual(self.report["diagnostics"], [])
        self.assertEqual(self.report["coverage_warnings"], [])
        monitor = select_symbol(self.graph, file="src/monitor.c", line=14)
        self.assertEqual(monitor["name"], "monitor_cells")
        local = traverse(self.graph, monitor["id"])
        names = {n["name"] for n in local["nodes"]}
        self.assertTrue({"check_cell_voltage", "read_cell_sample", "update_state"} <= names)
        edge = next(e for e in local["edges"] if e["target"] == "fn:external:update_state")
        self.assertEqual(edge["resolution"], "verified")
        self.assertEqual(edge["evidence"]["file"], "src/monitor.c")

    def test_static_duplicate_names_and_recursion(self):
        duplicates = [n for n in self.graph["nodes"] if n["name"] == "duplicate"]
        self.assertEqual(len(duplicates), 2)
        self.assertNotEqual(duplicates[0]["id"], duplicates[1]["id"])
        self.assertRaises(ValueError, select_symbol, self.graph, symbol="duplicate")
        recursion = next(e for e in self.graph["edges"] if e["source"] == "fn:static:src/edge_cases.c:recurse")
        self.assertEqual(recursion["target"], recursion["source"])

    def test_unresolved_calls(self):
        edges = [e for e in self.graph["edges"] if e["source"] in
                 {"fn:external:call_unavailable", "fn:external:call_indirect"}]
        self.assertEqual(len(edges), 2)
        self.assertTrue(all(e["resolution"] == "unresolved" for e in edges))
        self.assertTrue(any(e["target"].startswith("unresolved:") for e in edges))

    def test_depth_direction_and_limit(self):
        root = "fn:external:monitor_cells"
        self.assertEqual(len(traverse(self.graph, root, depth=0)["nodes"]), 1)
        self.assertEqual(len(traverse(self.graph, root, depth=1, max_nodes=2)["nodes"]), 2)
        expanded = traverse(self.graph, root, depth=3, direction="callees")
        self.assertIn("report_can", {n["name"] for n in expanded["nodes"]})

    def test_index_cache_and_report(self):
        result = index_repository(FIXTURE, self.index)
        self.assertEqual(result["cached"], result["files"])
        html = Path(self.tmp.name) / "report.html"
        write_html(self.graph, "fn:external:monitor_cells", FIXTURE, html)
        content = html.read_text()
        self.assertIn("Code Impact Explorer", content)
        self.assertIn("src/monitor.c", content)
        self.assertNotIn("https://", content)

    def test_safe_compiler_flags(self):
        source = FIXTURE / "src" / "monitor.c"
        flags, skipped = safe_compile_flags({"directory": str(FIXTURE),
            "arguments": ["clang", "-I", "include", "-DTEST=1", "-Xclang", "-load", "evil.so", "-c", str(source)]}, source)
        self.assertIn("-DTEST=1", flags)
        self.assertIn("-Xclang", skipped)
        self.assertNotIn("evil.so", flags)


if __name__ == "__main__":
    unittest.main()
