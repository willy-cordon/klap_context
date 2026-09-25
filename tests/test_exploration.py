"""End-to-end checks for the graph-to-context navigation boundary."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from klapcontext.agent.compiler import compile_context
from klapcontext.agent_context import render as agent_render
from klapcontext.context_builder import build
from klapcontext.detector import detect_project
from klapcontext.portal import render as portal_render


class GraphExplorationTests(unittest.TestCase):
    def test_csharp_graph_reaches_agent_and_portal(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            controller = root / "src" / "InfractionsController.cs"
            controller.parent.mkdir()
            controller.write_text("class InfractionsController {}")
            graph = {"nodes": [
                {"id": "controller", "label": "InfractionsController", "source_file": "src/InfractionsController.cs", "type": "class"},
                {"id": "list", "label": "List", "source_file": "src/InfractionsController.cs", "type": "method"},
                {"id": "service", "label": "FindInfractions", "source_file": "src/InfractionsController.cs", "type": "method"},
            ], "links": [{"source": "controller", "target": "list", "relation": "method"},
                         {"source": "list", "target": "service", "relation": "calls", "confidence": "EXTRACTED"}]}
            context = build(root, graph)
            files = context["system_model"]["exploration"]["files"]
            self.assertEqual(files[0]["symbols"][0]["members"][0]["name"], "List")
            self.assertEqual(context["system_model"]["exploration"]["call_paths"][0]["steps"][1]["name"], "FindInfractions")
            page = portal_render(context, agent_render(context), [])
            self.assertIn("InfractionsController.cs", page)
            self.assertIn("FindInfractions", page)
            self.assertIn("Archivos y símbolos", page)
            cache = root / ".klap"
            cache.mkdir()
            import json
            (cache / "context.json").write_text(json.dumps(context))
            task = compile_context(root, "InfractionsController", max_tokens=1000)
            self.assertEqual(task["read_first"][0]["path"], "src/InfractionsController.cs")

    def test_partial_coverage_does_not_claim_full_scan(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text("def run(): pass")
            context = build(root, {"nodes": [], "links": []})
            coverage = context["system_model"]["exploration"]["coverage"]
            self.assertEqual(coverage["status"], "PARTIAL")
            self.assertEqual(coverage["eligible_code_files"], 1)
            self.assertIn("Cobertura parcial", " ".join(context["system_model"]["unknowns"]))

    def test_nested_manifests_detect_web_stacks(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "api").mkdir()
            (root / "api" / "service.csproj").write_text('<Project Sdk="Microsoft.NET.Sdk.Web" />')
            stack, evidence = detect_project(root)
            self.assertIn("C#", stack["languages"])
            self.assertIn("ASP.NET", stack["frameworks"])
            self.assertEqual(evidence[0].path, "api/service.csproj")


if __name__ == "__main__":
    unittest.main()
