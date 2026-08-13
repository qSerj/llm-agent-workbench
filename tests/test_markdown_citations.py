import tempfile
import unittest
from pathlib import Path

from tools.check_markdown_citations import check_citations


class MarkdownCitationTests(unittest.TestCase):
    def test_accepts_existing_line_and_rejects_line_outside_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "src" / "Example.cs"
            source.parent.mkdir()
            source.write_text("first\nsecond\n", encoding="utf-8")
            valid = root / "valid.md"
            valid.write_text("See `src/Example.cs:2`.\n", encoding="utf-8")
            invalid = root / "invalid.md"
            invalid.write_text("See `src/Example.cs:3`.\n", encoding="utf-8")

            self.assertEqual(check_citations(valid, root)["verdict"], "PASS")
            result = check_citations(invalid, root)
            self.assertEqual(result["verdict"], "FAIL")
            self.assertEqual(result["checks"][0]["line_count"], 2)

    def test_requires_at_least_one_citation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document = root / "document.md"
            document.write_text("No source reference.\n", encoding="utf-8")

            self.assertEqual(check_citations(document, root)["verdict"], "FAIL")


if __name__ == "__main__":
    unittest.main()
