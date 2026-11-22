"""Current release identity must not relabel historical security evidence."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts import verify_release_candidate as verifier

ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / 'VERSION').read_text().strip()


class CurrentInventoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / 'sbom').mkdir()
        shutil.copyfile(ROOT / 'requirements.txt', self.root / 'requirements.txt')
        self.inventory = json.loads((ROOT / 'sbom/SBOM_CURRENT.cdx.json').read_text())

    def validate(self):
        (self.root / 'sbom/SBOM_CURRENT.cdx.json').write_text(json.dumps(self.inventory))
        verifier.check_current_sbom(self.root, VERSION)

    def test_declared_inventory_matches_current_release_without_claiming_resolution(self):
        self.validate()
        historical = json.loads((ROOT / 'sbom/SBOM_ROUND18.cdx.json').read_text())
        self.assertEqual(historical['metadata']['component']['version'], '0.9.0-1')
        self.assertNotEqual(historical['metadata']['component']['version'], VERSION)

    def test_previous_release_inventory_cannot_be_used_for_current_candidate(self):
        self.inventory['metadata']['component']['version'] = '0.9.0-1'
        with self.assertRaisesRegex(ValueError, 'version'):
            self.validate()

    def test_missing_direct_dependency_is_rejected(self):
        self.inventory['components'].pop()
        with self.assertRaisesRegex(ValueError, 'exactly'):
            self.validate()

    def test_declared_range_cannot_pretend_to_be_a_resolved_version(self):
        dependency = next(item for item in self.inventory['components'] if item['name'] == 'defusedxml')
        dependency['version'] = '0.7.1'
        with self.assertRaisesRegex(ValueError, 'invent'):
            self.validate()

    def test_unresolved_inventory_cannot_claim_wheel_hashes(self):
        self.inventory['components'][0]['hashes'] = [{'alg': 'SHA-256', 'content': 'a' * 64}]
        with self.assertRaisesRegex(ValueError, 'invent'):
            self.validate()

    def test_requirements_change_invalidates_source_inventory(self):
        requirements = self.root / 'requirements.txt'
        requirements.write_text(requirements.read_text().replace('pypdf==6.19.0', 'pypdf==6.19.1'))
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.validate()

    def test_missing_inventory_provenance_is_rejected(self):
        self.inventory['metadata']['properties'] = []
        with self.assertRaisesRegex(ValueError, 'unresolved'):
            self.validate()


class StaticManifestMetadataTests(unittest.TestCase):
    def test_changed_static_manifests_parse_and_deployment_uses_current_release(self):
        import yaml

        for relative in (
            'k8s/deployment.yaml', 'docker-compose.yml',
            '.github/workflows/ci-release.yml', 'openshift/cir-template.yaml',
            'charts/cybersecurity-incident-registry/Chart.yaml',
            'charts/cybersecurity-incident-registry/values.yaml',
        ):
            with self.subTest(manifest=relative):
                documents = list(yaml.safe_load_all((ROOT / relative).read_text()))
                self.assertTrue(documents)
                self.assertTrue(all(isinstance(document, dict) for document in documents))
        deployment = next(document for document in
                          yaml.safe_load_all((ROOT / 'k8s/deployment.yaml').read_text())
                          if document.get('kind') == 'Deployment')
        web = next(container for container in deployment['spec']['template']['spec']['containers']
                   if container['name'] == 'web')
        self.assertEqual(web['image'], f'desalvo/cybersecurity-incident-registry:{VERSION}')
        self.assertFalse({'APP_VERSION', 'APP_BUILD'} & {item['name'] for item in web['env']})


class ReviewedPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((ROOT / 'TRIVY_RISK_ACCEPTANCE_R8.json').read_text())

    def test_new_release_scope_preserves_historical_review_without_renewal(self):
        verifier.check_reviewed_policy(self.policy, VERSION)
        self.assertEqual(self.policy['reviewed_baseline']['release'], '0.9.0-1')
        self.assertEqual(self.policy['reviewed_baseline']['build'], '20260902')
        self.assertEqual(self.policy['valid_until'], '2026-10-20')
        self.assertEqual(self.policy['release_status'], 'review_required')

    def test_policy_scope_cannot_silently_apply_to_another_release(self):
        self.policy['release'] = '0.9.0-1'
        with self.assertRaisesRegex(ValueError, 'scope'):
            verifier.check_reviewed_policy(self.policy, VERSION)

    def test_changing_reviewed_build_does_not_pass_as_an_automatic_build(self):
        self.policy['build'] = (ROOT / 'BUILD').read_text().strip()
        with self.assertRaisesRegex(ValueError, 'baseline'):
            verifier.check_reviewed_policy(self.policy, VERSION)

    def test_malformed_or_missing_reviewed_baseline_is_rejected(self):
        for baseline in ({}, {'release': '0.9.0-1', 'build': '20260230'}, {'release': 'latest', 'build': '20260902'}):
            policy = copy.deepcopy(self.policy)
            policy['reviewed_baseline'] = baseline
            with self.subTest(baseline=baseline), self.assertRaises(ValueError):
                verifier.check_reviewed_policy(policy, VERSION)


if __name__ == '__main__':
    unittest.main()
