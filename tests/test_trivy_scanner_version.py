"""Keep every CIR security gate on the same reviewed Trivy release."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ("ci-security-fast.yml", "ci-release.yml", "security-review.yml")

class TrivyScannerVersionTests(unittest.TestCase):
    def test_all_workflows_use_reviewed_trivy_release(self):
        for name in WORKFLOWS:
            with self.subTest(workflow=name):
                content = (ROOT / ".github" / "workflows" / name).read_text()
                self.assertIn("version: v0.76.2", content)
                self.assertNotIn("version: v0.74.0", content)
                self.assertIn("aquasecurity/setup-trivy@81e514348e19b6112ce2a7e3ecbafe19c1e1f567", content)

if __name__ == "__main__":
    unittest.main()
