import unittest

from tools.run_opencode_stage import restrict_edits


class StagePermissionTests(unittest.TestCase):
    def test_restricts_edits_to_exact_stage_outputs(self):
        config = {"permission": {"edit": {"*": "deny", "docs/**": "allow"}}}

        restrict_edits(config, ["docs/review-findings.json"])

        self.assertEqual(
            config["permission"]["edit"],
            {"*": "deny", "docs/review-findings.json": "allow"},
        )

    def test_rejects_stage_without_output_allowlist(self):
        with self.assertRaisesRegex(ValueError, "allow-edit"):
            restrict_edits({"permission": {}}, [])

    def test_rejects_parent_path_and_glob(self):
        for path in ("../outside.md", "docs/*.md", "/tmp/output.md"):
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, "exact relative path"):
                    restrict_edits({"permission": {}}, [path])


if __name__ == "__main__":
    unittest.main()
