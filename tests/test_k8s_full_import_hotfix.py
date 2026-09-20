from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_kubernetes_data_layout_supports_atomic_full_import_staging():
    deployment = (ROOT / "k8s/deployment.yaml").read_text(encoding="utf-8")
    pvc = (ROOT / "k8s/pvc.yaml").read_text(encoding="utf-8")
    migration = (ROOT / "docs/MIGRATION.md").read_text(encoding="utf-8")

    assert "claimName: cir-data" in deployment
    assert "mountPath: /data}" in deployment
    for child in ("uploads", "logo", "form_templates", "sso_logos", "ssl", "backups", "ai_chatbot_docs"):
        assert f"value: /data/{child}" in deployment
        assert f"mountPath: /data/{child}" not in deployment
    for obsolete in ("cir-uploads", "cir-logo", "cir-form-templates", "cir-sso-logos", "cir-ssl-certs", "cir-backups", "cir-ai-chatbot-docs"):
        assert obsolete not in pvc
    assert "name: cir-data" in pvc
    assert "ReadWriteMany" in pvc
    assert "un unico PVC `cir-data`" in migration


def test_split_pvc_migration_job_is_example_only_and_not_kustomized():
    kustomization = (ROOT / "k8s/kustomization.yaml").read_text(encoding="utf-8")
    job = ROOT / "k8s/migrate-separated-pvcs-to-cir-data.example.yaml"
    assert job.is_file()
    assert job.name not in kustomization
    text = job.read_text(encoding="utf-8")
    assert "claimName: cir-data" in text
    assert "claimName: cir-uploads" in text
    assert "copy_tree /old/uploads /data/uploads" in text
