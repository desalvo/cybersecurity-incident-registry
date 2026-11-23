"""Actual workflow JSON exports carry the packaged release identity."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from release_metadata import read_release_metadata

ROOT = Path(__file__).resolve().parents[1]


class WorkflowReleaseMetadataTests(unittest.TestCase):
    def test_operational_and_defaults_workflow_exports_use_packaged_version_and_build(self):
        from flask import Flask
        from app.models import db, Tenant
        from app import routes

        with tempfile.TemporaryDirectory(prefix="cir-workflow-release-") as directory:
            app = Flask(__name__)
            app.config.update(
                SQLALCHEMY_DATABASE_URI="sqlite:///" + str(Path(directory) / "workflow.db"),
                SQLALCHEMY_TRACK_MODIFICATIONS=False,
            )
            db.init_app(app)
            expected = read_release_metadata(ROOT)
            with app.app_context():
                try:
                    db.create_all()
                    db.session.info["cir_defaults_suspended"] = True
                    tenants = [Tenant(name="default"),
                               Tenant(name="Tenants Default", is_system_defaults=True)]
                    db.session.add_all(tenants)
                    db.session.commit()
                    # Legacy globals must not replace metadata from VERSION/BUILD.
                    with patch.object(routes, "APP_VERSION", "0.9.0-1", create=True), \
                            patch.object(routes, "APP_BUILD", "20260902", create=True):
                        for tenant in tenants:
                            with self.subTest(tenant=tenant.name), routes.tenant_execution_context(tenant.id):
                                payload = json.loads(json.dumps(routes.build_workflow_export_payload()))
                                self.assertEqual(payload["application"]["version"], expected.version)
                                self.assertEqual(payload["application"]["build"], expected.build)
                                self.assertTrue(payload["application"]["version"])
                finally:
                    db.session.remove()
                    db.engine.dispose()


if __name__ == "__main__":
    unittest.main()
