import tempfile
import unittest
from pathlib import Path

from test_envelope import make_bundle
from workbench.envelope import build_legacy_opencode_envelope
from workbench.otel_projection import project_to_otel


class OtelProjectionSmokeTests(unittest.TestCase):
    def setUp(self):
        try:
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import SimpleSpanProcessor
            from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
                InMemorySpanExporter,
            )
        except ImportError as error:
            self.skipTest(f"optional OpenTelemetry SDK is unavailable: {error}")
        self.exporter = InMemorySpanExporter()
        self.provider = TracerProvider()
        self.provider.add_span_processor(SimpleSpanProcessor(self.exporter))

    def make_envelope(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        return build_legacy_opencode_envelope(make_bundle(Path(temporary.name)))

    def test_projects_identity_artifacts_observations_and_evaluation(self):
        envelope = self.make_envelope()
        envelope["stages"] = [
            {
                "id": "solver",
                "role": "SOLVER",
                "execution_id": "child:solver",
                "depends_on": [],
                "input_artifact_ids": ["task-prompt"],
                "output_artifact_ids": ["generated-document"],
            }
        ]

        trace_id, span_id = project_to_otel(
            envelope, self.provider.get_tracer("workbench-test")
        )

        spans = self.exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        span = next(item for item in spans if item.name == "task.execute")
        stage = next(item for item in spans if item.name == "stage.solver")
        self.assertEqual(span.name, "task.execute")
        self.assertEqual(stage.parent.span_id, span.context.span_id)
        self.assertEqual(stage.attributes["workbench.stage.id"], "solver")
        self.assertEqual(len(trace_id), 32)
        self.assertEqual(len(span_id), 16)
        event_names = [event.name for event in span.events]
        self.assertIn("workbench.artifact", event_names)
        self.assertIn("workbench.observation", event_names)
        self.assertIn("workbench.evaluation.result", event_names)
        self.assertNotIn("gen_ai.operation.name", span.attributes)


if __name__ == "__main__":
    unittest.main()
