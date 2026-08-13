import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from run_agent import build_opencode_config, collect_usage_from_jsonl


class TelemetryTests(unittest.TestCase):
    def collect(self, events):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            lines = [json.dumps(event) if isinstance(event, dict) else event for event in events]
            path.write_text("\n".join(lines), encoding="utf-8")
            return collect_usage_from_jsonl(path)

    def test_collects_tools_tokens_and_explicit_costs(self):
        usage = self.collect(
            [
                {"type": "tool_use", "part": {"state": {"status": "completed"}}},
                {"type": "tool_use", "part": {"state": {"status": "error"}}},
                {
                    "type": "step_finish",
                    "part": {
                        "tokens": {"input": 100, "output": 20, "reasoning": 5, "total": 125},
                        "cost": 0.001,
                    },
                },
                {
                    "type": "step_finish",
                    "part": {
                        "tokens": {"input": 200, "output": 30, "reasoning": 7, "total": 237},
                        "cost": 0.002,
                    },
                },
            ]
        )

        self.assertEqual(usage["tool_calls"], 2)
        self.assertEqual(usage["failed_tool_calls"], 1)
        self.assertEqual(usage["step_finishes"], 2)
        self.assertEqual(
            usage["summed_step_tokens"],
            {"input": 300, "output": 50, "reasoning": 12, "total": 362},
        )
        self.assertEqual(usage["last_reported_tokens"]["total"], 237)
        self.assertEqual(usage["total_reported_cost_usd"], 0.003)
        self.assertFalse(usage["cost_is_estimate"])

    def test_ignores_malformed_lines_and_preserves_unknown_metrics(self):
        usage = self.collect(
            [
                "not-json",
                {"type": "tool_use", "part": {}},
                {"type": "step_finish", "part": {}},
            ]
        )

        self.assertEqual(usage["tool_calls"], 1)
        self.assertEqual(usage["failed_tool_calls"], 0)
        self.assertIsNone(usage["summed_step_tokens"])
        self.assertIsNone(usage["total_reported_cost_usd"])
        self.assertIsNone(usage["cost_is_estimate"])


class ProviderConfigurationTests(unittest.TestCase):
    def args(self, provider, **overrides):
        values = {
            "provider": provider,
            "model": "test-model",
            "base_url": None,
            "provider_id": None,
            "provider_name": None,
            "api_key_env": None,
            "provider_context": None,
            "provider_output": None,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_lmstudio_uses_local_instance_alias(self):
        config, model_name = build_opencode_config(self.args("lmstudio"))

        self.assertEqual(model_name, "lmstudio/agent-bench-current")
        self.assertEqual(
            config["provider"]["lmstudio"]["options"]["baseURL"],
            "http://127.0.0.1:1234/v1",
        )

    def test_openrouter_uses_builtin_provider(self):
        config, model_name = build_opencode_config(self.args("openrouter"))

        self.assertEqual(model_name, "openrouter/test-model")
        self.assertEqual(config["model"], model_name)
        self.assertNotIn("provider", config)

    def test_compatible_provider_references_secret_by_environment_name(self):
        config, model_name = build_opencode_config(
            self.args(
                "compatible",
                base_url="https://example.invalid/v1",
                provider_id="example",
                provider_name="Example",
                api_key_env="EXAMPLE_API_KEY",
                provider_context=32768,
                provider_output=4096,
            )
        )

        provider = config["provider"]["example"]
        self.assertEqual(model_name, "example/test-model")
        self.assertEqual(provider["options"]["apiKey"], "{env:EXAMPLE_API_KEY}")
        self.assertNotIn("replace-me", json.dumps(config))
        self.assertEqual(
            provider["models"]["test-model"]["limit"],
            {"context": 32768, "output": 4096},
        )


if __name__ == "__main__":
    unittest.main()
