"""Offline installer regressions; real Helm rendering is an explicit separate gate."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts/cybersecurity-incident-registry"


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RENDER = load_script("render_openshift_template")
CHECK = load_script("check_installation_package")
PACKAGE = load_script("package_installers")
# Explicit non-deployable fixtures; never written to PRODUCTION_IMAGE_DIGEST.
FIXTURE = {"IMAGE_SHA256": "a" * 64, "EXISTING_SECRET": "test-secret"}


class ClusterInstallationTests(unittest.TestCase):
    def objects(self):
        return RENDER.render_template(FIXTURE)["items"]

    def web(self, objects):
        return next(obj for obj in objects if obj["kind"] == "Deployment")["spec"]["template"]["spec"]

    def test_supported_helm_version_is_checked(self):
        for version in ("v3.14.0", "v3.22.0+g1234567"):
            CHECK.validate_helm_version(version)
        for version in ("v2.17.0", "v3.13.9", "v4.0.0", "v3.22.0-rc1", "unknown"):
            with self.subTest(version=version), self.assertRaises(ValueError):
                CHECK.validate_helm_version(version)

    def test_required_installation_sources_are_present(self):
        CHECK.source_checks()

    def test_functional_version_does_not_follow_chart_rc_number(self):
        text = (CHART / "Chart.yaml").read_text()
        self.assertIn(f'appVersion: "{(ROOT / "VERSION").read_text().strip()}"', text)
        self.assertIn("version: 0.2.0-rc1", text)

    def test_openshift_objects_are_self_contained_and_hardened(self):
        objects = self.objects()
        CHECK.validate_objects(objects, "openshift")
        names = {obj["metadata"]["name"] for obj in objects}
        pod = self.web(objects)
        self.assertIn(pod["serviceAccountName"], names)
        self.assertTrue(all(vol.get("persistentVolumeClaim", {}).get("claimName", "cir") in names for vol in pod["volumes"]))
        self.assertEqual({obj["kind"] for obj in objects}, {"ServiceAccount", "PersistentVolumeClaim", "Deployment", "Service", "Route"})

    def test_template_requires_approved_digest_and_existing_secret(self):
        for params in ({}, {"IMAGE_SHA256":"a" * 64}, {"EXISTING_SECRET":"cir"}):
            with self.subTest(params=params), self.assertRaises(ValueError):
                RENDER.render_template(params)

    def test_template_rejects_mutable_pending_and_malformed_digest(self):
        for digest in ("latest", "PENDING_HOTFIX_REBUILD", "sha256:" + "a" * 64, "A" * 64, "a" * 63):
            with self.subTest(digest=digest), self.assertRaises(ValueError):
                RENDER.render_template(dict(FIXTURE, IMAGE_SHA256=digest))

    def test_template_rejects_repository_tag_credentials_and_shell_text(self):
        for repo in ("desalvo/cir:latest", "https://user:password@example.org/cir", 'cir; echo x', 'cir\nimage: bad'):
            with self.subTest(repo=repo), self.assertRaises(ValueError):
                RENDER.render_template(dict(FIXTURE, IMAGE_REPOSITORY=repo))

    def test_template_rejects_unknown_parameters(self):
        with self.assertRaisesRegex(ValueError, "Unknown"):
            RENDER.render_template(dict(FIXTURE, RUN_AS_ROOT="true"))

    def test_proxy_configuration_rejects_all_networks(self):
        for cidrs in ("0.0.0.0/0", "::/0", "invalid"):
            with self.subTest(cidrs=cidrs), self.assertRaises(ValueError):
                RENDER.render_template(dict(FIXTURE, TRUSTED_PROXY_CIDRS=cidrs))
        RENDER.render_template(dict(FIXTURE, TRUSTED_PROXY_CIDRS="10.0.0.0/24,fd00::/64"))

    def test_template_does_not_embed_or_generate_secrets(self):
        objects = self.objects()
        self.assertFalse(any(obj["kind"] == "Secret" for obj in objects))
        env = {item["name"]:item for item in self.web(objects)["containers"][0]["env"]}
        for name in ("DATABASE_URL", "SECRET_KEY", "ADMIN_INITIAL_PASSWORD", "SETTING_ENCRYPTION_KEY"):
            self.assertNotIn("value", env[name])
            self.assertEqual(env[name]["valueFrom"]["secretKeyRef"]["name"], "test-secret")

    def test_openshift_does_not_pin_uid_or_request_scc_bypass(self):
        objects = self.objects()
        pod = self.web(objects)
        for context in (pod["securityContext"], pod["containers"][0]["securityContext"]):
            self.assertFalse({"runAsUser", "runAsGroup", "fsGroup"} & set(context))
        self.assertFalse(any(obj["kind"] in {"ClusterRoleBinding", "SecurityContextConstraints"} for obj in objects))

    def test_verifier_rejects_capability_addition_and_root(self):
        objects = self.objects()
        self.web(objects)["containers"][0]["securityContext"]["capabilities"]["add"] = ["CHOWN"]
        with self.assertRaises(ValueError):
            CHECK.validate_objects(objects, "openshift")
        objects = self.objects()
        self.web(objects)["securityContext"]["runAsUser"] = 0
        with self.assertRaises(ValueError):
            CHECK.validate_objects(objects, "openshift")

    def test_verifier_rejects_writeable_root_and_untagged_security(self):
        for field, value in (("readOnlyRootFilesystem",False),("allowPrivilegeEscalation",True),("runAsNonRoot",False)):
            objects = self.objects()
            self.web(objects)["containers"][0]["securityContext"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                CHECK.validate_objects(objects, "openshift")

    def test_verifier_rejects_mutable_image_even_with_other_security(self):
        objects = self.objects()
        self.web(objects)["containers"][0]["image"] = "desalvo/cybersecurity-incident-registry:latest"
        with self.assertRaisesRegex(ValueError, "immutable"):
            CHECK.validate_objects(objects, "openshift")

    def test_verifier_rejects_plain_http_route(self):
        objects = self.objects()
        next(obj for obj in objects if obj["kind"] == "Route")["spec"]["tls"]["insecureEdgeTerminationPolicy"] = "Allow"
        with self.assertRaises(ValueError):
            CHECK.validate_objects(objects, "openshift")

    def test_postgresql_template_waits_for_final_tcp_server(self):
        text = (CHART / "templates/postgresql.yaml").read_text()
        self.assertEqual(text.count('pg_isready -h 127.0.0.1'), 3)
        for item in ("startupFailureThreshold", "PGCTLTIMEOUT", "/var/lib/postgresql/18/docker", "mountPath: /var/lib/postgresql", "mountPath: /var/run/postgresql", "mountPath: /tmp", "mountPath: /dev/shm"):
            self.assertIn(item, text)
        self.assertNotIn("chown", text)
        self.assertNotIn("initContainers", text)

    def test_web_liveness_does_not_use_busy_request_workers(self):
        web = self.web(self.objects())["containers"][0]
        self.assertIn("tcpSocket", web["livenessProbe"])
        self.assertIn("httpGet", web["readinessProbe"])
        self.assertGreaterEqual(web["startupProbe"]["failureThreshold"] * web["startupProbe"]["periodSeconds"], 300)

    def test_chart_schema_rejects_missing_digest_and_unsafe_overrides(self):
        try:
            import yaml
            import jsonschema
        except ImportError:
            self.skipTest("PyYAML and jsonschema required for this full schema check")
        values = yaml.safe_load((CHART / "values.yaml").read_text())
        schema = json.loads((CHART / "values.schema.json").read_text())
        jsonschema.Draft7Validator.check_schema(schema)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(values, schema)
        values["image"]["digest"] = "sha256:" + "a" * 64
        values["existingSecret"] = "test-secret"
        jsonschema.validate(values, schema)
        mutations = [
            lambda obj: obj.update(extraEnv=[{"name":"CIR_PRODUCTION","value":"0"}]),
            lambda obj: obj.update(replicaCount=2),
            lambda obj: obj["image"].update(digest="latest"),
            lambda obj: obj["kubernetesSecurity"].update(runAsUser=0),
            lambda obj: obj["database"].update(mode="sqlite"),
            lambda obj: obj["database"].update(mode="internal"),
            lambda obj: obj["route"].update(enabled=True),
            lambda obj: obj["ingress"].update(enabled=True),
        ]
        for mutate in mutations:
            invalid = copy.deepcopy(values)
            mutate(invalid)
            with self.subTest(values=invalid), self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate(invalid, schema)

    def test_chart_accepts_openshift_and_explicit_internal_database(self):
        try:
            import yaml
            import jsonschema
        except ImportError:
            self.skipTest("PyYAML and jsonschema required for this full schema check")
        values = yaml.safe_load((CHART / "values.yaml").read_text())
        values.update(platform="openshift", existingSecret="cir-secrets")
        values["image"]["digest"] = "sha256:" + "a" * 64
        values["route"]["enabled"] = True
        values["database"]["mode"] = "internal"
        values["database"]["internal"]["image"]["digest"] = "sha256:" + "b" * 64
        values["database"]["internal"]["existingSecret"] = "postgres-secrets"
        jsonschema.validate(values, json.loads((CHART / "values.schema.json").read_text()))

    def test_installer_packaging_is_deterministic_and_checksums_match(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            a = PACKAGE.build_package(Path(first))
            b = PACKAGE.build_package(Path(second))
            for key in ("chart", "index", "zip", "checks"):
                self.assertEqual(Path(a[key]).read_bytes(), Path(b[key]).read_bytes())
            chart = Path(a["chart"])
            index = json.loads(Path(a["index"]).read_text())
            entry = index["entries"]["cybersecurity-incident-registry"][0]
            self.assertEqual(entry["appVersion"], (ROOT / "VERSION").read_text().strip())
            self.assertEqual(entry["digest"], hashlib.sha256(chart.read_bytes()).hexdigest())
            self.assertEqual(entry["urls"], [chart.name])
            with tarfile.open(chart, "r:gz") as archive:
                names = archive.getnames()
                self.assertIn("cybersecurity-incident-registry/values.schema.json", names)
                self.assertTrue(all(name.startswith("cybersecurity-incident-registry/") for name in names))
                self.assertFalse(any("__pycache__" in name or ".." in Path(name).parts for name in names))
            with zipfile.ZipFile(a["zip"]) as archive:
                names = archive.namelist()
                self.assertTrue(any(name.endswith("scripts/install_cluster.sh") for name in names))
                self.assertTrue(any(name.endswith("openshift/cir-template.yaml") for name in names))
                for metadata_name in ("VERSION", "BUILD", "release_metadata.py"):
                    archived_name = next(name for name in names if name.endswith("/" + metadata_name))
                    self.assertEqual(archive.read(archived_name), (ROOT / metadata_name).read_bytes())
            evidence = json.loads(Path(a["checks"]).read_text())
            self.assertEqual(evidence["functional_version"], (ROOT / "VERSION").read_text().strip())
            self.assertEqual(evidence["build"], (ROOT / "BUILD").read_text().strip())
            self.assertEqual(evidence["helm_render"], "NOT_RUN")
            self.assertEqual(evidence["cluster_admission"], "NOT_RUN")
            self.assertFalse(evidence["repository_published"])

    def test_packager_rejects_insecure_repository_url(self):
        with tempfile.TemporaryDirectory() as directory:
            for url in ("http://charts.example.org", "https://user:password@charts.example.org", "https://charts.example.org/?token=secret"):
                with self.subTest(url=url), self.assertRaises(ValueError):
                    PACKAGE.build_package(Path(directory), url)

    def test_cli_is_render_only_without_apply(self):
        text = (ROOT / "scripts/install_cluster.sh").read_text()
        self.assertIn("APPLY=0", text)
        self.assertIn('if [[ "$APPLY" == 0 ]]; then', text)
        self.assertIn("--dry-run=server", text)
        self.assertIn("--atomic --wait", text)
        self.assertNotIn("docker build", text)
        result = subprocess.run(["bash",str(ROOT / "scripts/install_cluster.sh"),"--help"],text=True,capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_ci_requires_real_helm_before_tests_and_publication(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML required for workflow parsing")
        workflow = yaml.safe_load((ROOT / ".github/workflows/ci-release.yml").read_text())
        job = workflow["jobs"]["quality-gates"]
        steps = job["steps"]
        gate = next(step for step in steps if step.get("name") == "Verify Helm and OpenShift installation renders")
        self.assertIn("helm version --short", gate["run"])
        self.assertIn("check_installation_package.py --require-helm", gate["run"])
        self.assertFalse(gate.get("continue-on-error", False))
        self.assertNotIn("if", gate)
        test_step = next(step for step in steps if step.get("name") == "Run complete pytest suite")
        self.assertLess(steps.index(gate), steps.index(test_step))
        self.assertIn("quality-gates", workflow["jobs"]["docker-release"]["needs"])
        artifact = next(step for step in steps if step.get("name") == "Upload installation packages")
        self.assertEqual(artifact["with"]["if-no-files-found"], "error")

    def test_entrypoint_validates_graceful_timeout_before_startup(self):
        entrypoint = ROOT / "docker-entrypoint.sh"
        self.assertEqual(entrypoint.read_text().count('--graceful-timeout "$GUNICORN_GRACEFUL_TIMEOUT"'), 2)
        for timeout in ("0", "-1", "36001", "bad", "1; echo unsafe"):
            with self.subTest(timeout=timeout):
                result = subprocess.run(["sh", str(entrypoint)],env=dict(os.environ,GUNICORN_GRACEFUL_TIMEOUT=timeout),text=True,capture_output=True,timeout=5)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("GUNICORN_GRACEFUL_TIMEOUT", result.stderr)

    @unittest.skipUnless(shutil.which("helm"), "Real Helm is not installed; --require-helm is an outstanding release gate")
    def test_real_helm_lints_renders_all_platform_and_database_modes(self):
        CHECK.helm_checks()


if __name__ == "__main__":
    unittest.main()
