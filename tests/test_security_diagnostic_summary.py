import json
import tempfile
import unittest
from pathlib import Path
from scripts.summarize_security_diagnostic import summarize


class SummaryTests(unittest.TestCase):
    def test_empty(self):
        with tempfile.TemporaryDirectory() as d:
            x = summarize(Path(d))
            self.assertEqual(x["reports"], [])
            self.assertFalse(x["debian_evidence"]["debian-policy.txt"]["present"])

    def test_counts(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "linux-amd64.json"
            p.write_text(json.dumps({"Results": [{"Vulnerabilities": [
                {"Severity": "HIGH", "VulnerabilityID": "CVE-X", "PkgName": "a"},
                {"Severity": "CRITICAL", "VulnerabilityID": "CVE-X", "PkgName": "b", "FixedVersion": "2"},
                {"Severity": "LOW", "VulnerabilityID": "CVE-Y", "PkgName": "c"}]}]}))
            x = summarize(Path(d))["reports"][0]
            self.assertEqual((x["high"], x["critical"], x["unique_cves"], x["fixed_version_reported"]), (1, 1, 1, 1))
