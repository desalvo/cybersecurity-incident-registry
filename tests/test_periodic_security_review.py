"""Periodic security review preserves production gates and cannot publish."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

from scripts.review_production_target import resolve_target

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/review_production_target.py'


class ProductionReviewTargetTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='cir-security-review-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_only_recorded_digest_is_used_without_mutable_tag_fallback(self):
        for image in ('desalvo/cybersecurity-incident-registry@sha256:' + 'a' * 64,
                      'registry.example:5000/team/cir@sha256:' + 'b' * 64):
            with self.subTest(image=image):
                (self.root / 'PRODUCTION_IMAGE_DIGEST').write_text(image + '\n')
                self.assertEqual(resolve_target(self.root), image)

    def test_pending_empty_invalid_and_mutable_references_are_blocked(self):
        for value in ('PENDING_HOTFIX_REBUILD', '', 'desalvo/cir:latest', 'desalvo/cir@sha256:abc',
                      'desalvo/cir@sha256:' + 'a' * 64 + '\nimage=unreviewed',
                      'desalvo//cir@sha256:' + 'a' * 64):
            with self.subTest(value=value):
                (self.root / 'PRODUCTION_IMAGE_DIGEST').write_text(value)
                with self.assertRaises(ValueError):
                    resolve_target(self.root)

    def test_pending_target_reports_failure_and_never_emits_scan_target(self):
        target = self.root / 'PRODUCTION_IMAGE_DIGEST'
        target.write_text('PENDING_HOTFIX_REBUILD\n')
        before = target.read_bytes()
        output, report, summary = [self.root / name for name in ('output', 'report.json', 'summary')]
        result = subprocess.run([sys.executable, str(SCRIPT), '--root', str(self.root),
                                 '--github-output', str(output), '--report', str(report), '--summary', str(summary)],
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('PENDING_HOTFIX_REBUILD', result.stderr)
        self.assertFalse(output.exists())
        self.assertEqual(json.loads(report.read_text())['status'], 'blocked')
        self.assertFalse(json.loads(report.read_text())['production_approval'])
        self.assertIn('blocked', summary.read_text())
        self.assertEqual(target.read_bytes(), before)

    def test_resolved_target_is_not_misreported_as_gate_or_production_approval(self):
        image = 'desalvo/cir@sha256:' + 'a' * 64
        (self.root / 'PRODUCTION_IMAGE_DIGEST').write_text(image + '\n')
        output, report = self.root / 'output', self.root / 'report.json'
        result = subprocess.run([sys.executable, str(SCRIPT), '--root', str(self.root),
                                 '--github-output', str(output), '--report', str(report)],
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output.read_text(), 'image=' + image + '\n')
        self.assertEqual(json.loads(report.read_text())['status'], 'target-resolved')
        self.assertFalse(json.loads(report.read_text())['production_approval'])
        self.assertIn('gates still need to pass', result.stdout)


class PeriodicWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (ROOT / '.github/workflows/security-review.yml').read_text()
        cls.workflow = yaml.safe_load(cls.text)
        cls.release = yaml.safe_load((ROOT / '.github/workflows/ci-release.yml').read_text())

    def test_weekly_and_manual_review_is_read_only_and_main_only(self):
        triggers = self.workflow.get('on', self.workflow.get(True))
        self.assertEqual(set(triggers), {'schedule', 'workflow_dispatch'})
        self.assertEqual(triggers['schedule'], [{'cron': '15 6 * * 1'}])
        self.assertEqual(self.workflow['permissions'], {'contents': 'read'})
        for name, job in self.workflow['jobs'].items():
            self.assertIn("github.ref == 'refs/heads/main'", job['if'])
            if name == 'notify':
                self.assertEqual(job['permissions'], {'contents': 'read', 'issues': 'write'})
                self.assertIn('always()', job['if'])
            else:
                self.assertNotIn('permissions', job)

    def test_platforms_are_reviewed_independently_without_short_circuiting(self):
        job = self.workflow['jobs']['production-image']
        self.assertIs(job['strategy']['fail-fast'], False)
        rows = job['strategy']['matrix']['include']
        self.assertEqual({row['platform'] for row in rows}, {'linux/amd64', 'linux/arm64'})
        self.assertNotIn('needs', job)
        gate = next(step for step in job['steps'] if 'run_trivy_production_gate.sh' in step.get('run', ''))
        self.assertEqual(gate['env']['CIR_TRIVY_PLATFORMS'], '${{ matrix.platform }}')
        self.assertEqual(gate['env']['CIR_PRODUCTION_IMAGE'], '${{ steps.target.outputs.image }}')
        self.assertEqual(gate['run'], 'bash ./scripts/run_trivy_production_gate.sh "$CIR_PRODUCTION_IMAGE"')

    def test_pending_digest_preflight_precedes_trivy_and_all_gate_failures_propagate(self):
        steps = self.workflow['jobs']['production-image']['steps']
        target = next(i for i, step in enumerate(steps) if step.get('id') == 'target')
        scan = next(i for i, step in enumerate(steps) if 'run_trivy_production_gate.sh' in step.get('run', ''))
        self.assertLess(target, scan)
        self.assertIn('scripts/review_production_target.py', steps[target]['run'])
        for job in self.workflow['jobs'].values():
            for step in job['steps']:
                self.assertFalse(step.get('continue-on-error', False))
                self.assertNotIn('|| true', step.get('run', ''))
        self.assertNotIn('--ignore-unfixed', self.text)
        self.assertNotIn('--ignore-vuln', self.text)

    def test_scanner_matches_release_pin_and_current_requirements_are_audited(self):
        release = next(step for step in self.release['jobs']['docker-release']['steps']
                       if step.get('uses', '').startswith('aquasecurity/setup-trivy@'))
        review = next(step for step in self.workflow['jobs']['production-image']['steps']
                      if step.get('uses', '').startswith('aquasecurity/setup-trivy@'))
        self.assertEqual(review['uses'], release['uses'])
        self.assertEqual(review['with']['version'], release['with']['version'])
        dependency_commands = '\n'.join(step.get('run', '') for step in self.workflow['jobs']['dependencies']['steps'])
        self.assertIn('pip install -r requirements.txt pip-audit', dependency_commands)
        self.assertIn('python -m pip check', dependency_commands)
        self.assertIn('./scripts/run_sca.sh', dependency_commands)

    def test_workflow_has_evidence_and_summaries_but_no_publish_or_auto_acceptance(self):
        commands = '\n'.join(step.get('run', '') for job in self.workflow['jobs'].values() for step in job['steps'])
        for forbidden in ('docker build', 'build-push-action', 'imagetools', 'record_production_digest',
                          'git push', 'gh pr', 'gh issue', 'gh api', 'CIR_TRIVY_POLICY='):
            self.assertNotIn(forbidden, commands)
        for name, job in self.workflow['jobs'].items():
            if name == 'notify':
                self.assertEqual(job['permissions']['issues'], 'write')
                self.assertIn('scripts/notify_security_issue.py', '\n'.join(step.get('run', '') for step in job['steps']))
                continue
            uploads = [step for step in job['steps'] if step.get('uses', '').startswith('actions/upload-artifact@')]
            self.assertEqual(len(uploads), 1)
            self.assertEqual(uploads[0]['if'], 'always()')
            summaries = [step for step in job['steps'] if '$GITHUB_STEP_SUMMARY' in step.get('run', '')]
            self.assertTrue(summaries)


if __name__ == '__main__':
    unittest.main()
