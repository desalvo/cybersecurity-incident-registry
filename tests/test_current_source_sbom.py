"""An unresolved source inventory must stay distinct from installed evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from scripts import generate_sbom

ROOT = Path(__file__).resolve().parents[1]


class DeclaredSourceInventoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.requirements = Path(temporary.name) / 'requirements.txt'

    def test_source_generation_never_reads_installed_packages_or_wheel_evidence(self):
        self.requirements.write_text('pypdf==6.19.0\ndefusedxml>=0.7.1,<0.8\n')
        with patch.object(generate_sbom, '_installed_distributions', side_effect=AssertionError('no installed lookup')) as installed:
            with patch.object(generate_sbom, '_wheel_evidence', side_effect=AssertionError('no wheel lookup')) as wheels:
                inventory = generate_sbom.build_declared_sbom(self.requirements)
        installed.assert_not_called()
        wheels.assert_not_called()
        properties = {item['name']: item['value'] for item in inventory['metadata']['properties']}
        self.assertEqual(properties['cir:inventory-source'], 'declared-requirements')
        self.assertEqual(properties['cir:resolution-status'], 'not-resolved')
        self.assertEqual(properties['cir:source-requirements-sha256'], hashlib.sha256(self.requirements.read_bytes()).hexdigest())
        self.assertTrue(all('hashes' not in component for component in inventory['components']))

    def test_only_exact_pins_have_versions_and_versioned_package_urls(self):
        self.requirements.write_text('pypdf==6.19.0\ndefusedxml>=0.7.1,<0.8\nFlask==3.*\nqrcode[pil]==8.2\n')
        inventory = generate_sbom.build_declared_sbom(self.requirements)
        components = {canonicalize_name(item['name']): item for item in inventory['components']}
        self.assertEqual(components['pypdf']['version'], '6.19.0')
        self.assertEqual(components['pypdf']['purl'], 'pkg:pypi/pypdf@6.19.0')
        for name in ('defusedxml', 'flask'):
            self.assertNotIn('version', components[name])
            self.assertNotIn('@', components[name]['purl'])
        qrcode_properties = {item['name']: item['value'] for item in components['qrcode']['properties']}
        self.assertEqual(qrcode_properties['cir:declared-requirement'], 'qrcode[pil]==8.2')

    def test_canonical_duplicate_declarations_are_rejected(self):
        self.requirements.write_text('Flask==3.1.3\nflask==3.1.3\n')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            generate_sbom.build_declared_sbom(self.requirements)

    def test_current_source_artifact_is_reproducible_from_current_requirements_and_version(self):
        expected = generate_sbom.build_declared_sbom(ROOT / 'requirements.txt')
        actual = json.loads((ROOT / 'sbom/SBOM_CURRENT.cdx.json').read_text())
        self.assertEqual(actual, expected)
        self.assertEqual(actual['metadata']['component']['version'], (ROOT / 'VERSION').read_text().strip())
        declared = generate_sbom._read_requirements(ROOT / 'requirements.txt')
        self.assertEqual({canonicalize_name(item['name']) for item in actual['components']},
                         {canonicalize_name(req.name) for req in declared})

    def test_resolved_generation_still_rejects_an_environment_with_outdated_pins(self):
        installed = {'pypdf': SimpleNamespace(version='6.16.2', metadata={'Name': 'pypdf'}, requires=[])}
        with self.assertRaisesRegex(RuntimeError, 'does not satisfy'):
            generate_sbom._resolve_graph([Requirement('pypdf==6.19.0')], installed)


if __name__ == '__main__':
    unittest.main()
