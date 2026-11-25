#!/usr/bin/env python3
"""Isolated synthetic fixture for real-application documentation captures.

This module has no production entry point. Its caller must supply a new private
directory. It never opens a caller-supplied DATABASE_URL or seeds an existing DB.
Credentials stay in memory and are deliberately absent from capture artifacts.
"""
from __future__ import annotations

import contextlib
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import secrets
from urllib.parse import urlparse

FIXTURE_ID = "cir-ui-documentation-v1"
STORAGE_ENV = {
    "UPLOAD_DIR": "uploads", "LOGO_DIR": "logos", "SSO_LOGO_DIR": "sso-logos",
    "FORM_TEMPLATE_DIR": "form-templates", "BACKUP_DIR": "backups",
    "AI_CHATBOT_DOC_DIR": "knowledge", "SSL_DIR": "ssl",
}


@contextlib.contextmanager
def isolated_environment(directory: Path):
    """Override inherited production endpoints before importing the app."""
    directory = Path(directory).resolve()
    if not directory.is_dir() or any(directory.iterdir()):
        raise ValueError("Documentation fixture requires a new empty directory")
    password = secrets.token_urlsafe(32) + "aA1!"
    secret = secrets.token_urlsafe(64)
    encryption_key = secrets.token_urlsafe(64)
    overrides = {
        "DATABASE_URL": "sqlite:///" + str(directory / "documentation.sqlite"),
        "SECRET_KEY": secret, "SETTING_ENCRYPTION_KEY": encryption_key,
        "ADMIN_INITIAL_PASSWORD": password,
        "CIR_DISABLE_BACKGROUND_SCHEDULERS": "1", "CIR_DISABLE_CSRF": "0",
        "CIR_PRODUCTION": "0", "FLASK_ENV": "development",
        "SESSION_COOKIE_SECURE": "0", "CIR_TRUSTED_PROXIES": "",
        **{key: str(directory / name) for key, name in STORAGE_ENV.items()},
    }
    # The application's *_FILE mechanism must not inherit a production secret.
    clear = {name + "_FILE" for name in overrides}
    clear.update({"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy",
                  "https_proxy", "all_proxy", "CONTENT_SECURITY_POLICY"})
    old = {key: os.environ.get(key) for key in set(overrides) | clear | {"NO_PROXY", "no_proxy"}}
    try:
        for key in clear:
            os.environ.pop(key, None)
        os.environ.update(overrides)
        os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"
        yield {"password": password, "secret": secret, "encryption_key": encryption_key,
               "root": directory}
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def seed_documentation_app(directory: Path, password: str, provider_url: str):
    """Create app normally, then add explicitly fictional records to its new DB."""
    directory = Path(directory).resolve()
    expected = "sqlite:///" + str(directory / "documentation.sqlite")
    if os.environ.get("DATABASE_URL") != expected or (directory / "documentation.sqlite").exists():
        raise ValueError("Refusing to seed an existing or non-fixture database")
    parsed = urlparse(provider_url)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.path != "/api/chat":
        raise ValueError("Only the isolated loopback AI fixture is allowed")

    from app import create_app
    from app.auth import hash_password
    from app.models import (Action, AIChatbotDocument, ConfigLabel, FormTemplateBinary,
                            FormTemplateConfig, FormFieldMapping, Incident, IncidentWorkflowStep,
                            NotificationTemplate, NotificationType, Person,
                            Setting, Tenant, User, UserTenantRole, db)
    from app.workflow_lifecycle import ensure_workflow_state
    from pypdf import PdfWriter

    app = create_app()
    fixture_time = (datetime.now(timezone.utc).replace(tzinfo=None, second=0, microsecond=0)
                    - timedelta(hours=2, minutes=18))
    # Real request handling, auth, CSRF, CSP and role/tenant checks remain active.
    app.config.update(TESTING=False, PROPAGATE_EXCEPTIONS=False)
    with app.app_context():
        assert app.config["SQLALCHEMY_DATABASE_URI"] == expected
        tenant = Tenant.query.filter_by(name="default").one()
        other = Tenant(name="laboratorio-demo", description="Tenant fittizio per test UI")
        db.session.add(other)
        db.session.flush()
        users = {}
        for username, name, role, owner in (
            ("demo-supervisor", "Admin operativo", "superuser", tenant),
            ("demo-tenant-admin", "Amministratore tenant demo", "admin", tenant),
            ("demo-reader", "Lettore demo", "reader", tenant),
            ("demo-reader-alt", "Lettore laboratorio demo", "reader", other),
        ):
            user = User(username=username, name=name, email=username + "@example.invalid",
                        auth_provider="local", is_ldap=False, role=role,
                        tenant_id=owner.id, default_tenant_id=owner.id,
                        password_hash=hash_password(password), mfa_enabled=False)
            db.session.add(user)
            db.session.flush()
            db.session.add(UserTenantRole(user_id=user.id, tenant_id=owner.id, role=role))
            users[username] = user

        def setting(key, value, owner=tenant):
            db.session.merge(Setting(key=f"tenant:{owner.id}:{key}", value=str(value)))

        # Use a packaged CIR logo as the explicitly configured fixture logo;
        # an unconfigured /logo correctly returns 404 in a fresh installation.
        logo = Path(app.config["LOGO_DIR"]) / "documentation-logo.png"
        logo.write_bytes((Path(app.static_folder) / "help" / "app-logo.png").read_bytes())
        db.session.merge(Setting(key="logo_path", value=str(logo)))

        # No setting for global_ui_mode: captures prove the application's NEW
        # default is modern, rather than making the fixture force the result.
        if db.session.get(Setting, "global_ui_mode") is not None:
            raise RuntimeError("Fresh fixture unexpectedly has an explicit UI mode")
        for key, value in {
            "plugin_ai_chatbot_enabled": "1", "ai_chatbot_engine": "ollama",
            "ai_chatbot_ollama_endpoint": provider_url,
            "ai_chatbot_ollama_model": FIXTURE_ID,
            "ai_chatbot_include_database_context": "0",
            "structure_name": "Laboratorio dimostrativo CIR",
            "setup_wizard_completed": "1", "smtp_host": "", "ldap_enabled": "0",
        }.items():
            setting(key, value)
        setting("plugin_ai_chatbot_enabled", "0", other)
        setting("sso_profiles_json", json.dumps([{
            "id": "documentation-demo", "sso_enabled": "1",
            "sso_provider_name": "SSO dimostrativo", "sso_client_id": "documentation-demo",
            "sso_client_secret": "", "sso_authorization_url": "https://sso.example.invalid/authorize",
            "sso_token_url": "https://sso.example.invalid/token",
            "sso_userinfo_url": "https://sso.example.invalid/userinfo", "sso_scopes": "openid profile email",
        }]))

        category = ConfigLabel(tenant_id=tenant.id, kind="category",
                               value="Gestione data breach · esempio", description="Workflow didattico fittizio")
        severity = ConfigLabel.query.filter_by(tenant_id=tenant.id, kind="severity", value="alta").first()
        if severity is None:
            severity = ConfigLabel(tenant_id=tenant.id, kind="severity", value="alta")
            db.session.add(severity)
        db.session.add(category)
        db.session.flush()
        titles = ["Informazione iniziale", "Conservazione delle evidenze",
                  "Scheda di valutazione", "Notifica al responsabile"]
        labels = []
        for index, title in enumerate(titles):
            # Bootstrap may have already installed the standard action labels.
            # Reuse their primary keys instead of violating the tenant/kind/value
            # unique constraint when the screenshot fixture is seeded.
            label = ConfigLabel.query.filter_by(
                tenant_id=tenant.id, kind="action_label", value=title
            ).first()
            if label is None:
                label = ConfigLabel(tenant_id=tenant.id, kind="action_label", value=title)
                db.session.add(label)
            label.description = "Configurazione dimostrativa"
            label.description_required = index == 1
            label.default_exportable = True
            label.max_completion_hours = 4 if index == 1 else 0
            labels.append(label)
        db.session.flush()
        template = "documentation-valutazione"
        # A genuine AcroForm, not a rendered imitation: three fields and their
        # database mappings are inspected in the live modules/configuration UI.
        # The fixture never includes real incident identifiers or personal data.
        from reportlab.pdfgen import canvas
        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=(595, 842))
        pdf.setTitle("Scheda PDF compilabile - laboratorio CIR")
        pdf.setFont("Helvetica-Bold", 17)
        pdf.drawString(48, 782, "CIR - Modello PDF di prova")
        for y, label, field in (
            (704, "Riferimento incidente", "RIFERIMENTO"),
            (614, "Descrizione sintetica", "DESCRIZIONE"),
            (524, "Data di apertura", "DATA_INIZIO"),
        ):
            pdf.setFont("Helvetica", 11)
            pdf.drawString(48, y + 32, label)
            pdf.acroForm.textfield(name=field, tooltip=label, x=48, y=y,
                                   width=490, height=25, borderWidth=1,
                                   fontName="Helvetica", fontSize=10,
                                   forceBorder=True)
        pdf.showPage()
        pdf.save()
        pdf_bytes = buffer.getvalue()
        from pypdf import PdfReader
        assert set(PdfReader(io.BytesIO(pdf_bytes)).get_fields()) == {
            "RIFERIMENTO", "DESCRIZIONE", "DATA_INIZIO"
        }, "The documentation PDF fixture must contain three real AcroForm fields"
        (Path(app.config["FORM_TEMPLATE_DIR"]) / (template + ".pdf")).write_bytes(pdf_bytes)
        db.session.add(FormTemplateConfig(template_name=template, owner_tenant_id=tenant.id,
                                           notification_tags="documentation-notice"))
        db.session.add(FormTemplateBinary(template_name=template, filename=template + ".pdf", pdf_data=pdf_bytes))
        for template_field, db_field in (
            ("RIFERIMENTO", "reference"),
            ("DESCRIZIONE", "description"),
            ("DATA_INIZIO", "start_date"),
        ):
            db.session.add(FormFieldMapping(
                template_name=template, template_field=template_field, db_field=db_field
            ))
        # Real Alfresco configuration screen with entirely fictional values:
        # no credential or endpoint is ever contacted by this fixture.
        for key, value in {
            "plugin_alfresco_enabled": "1",
            "alfresco_base_url": "https://alfresco.example.invalid",
            "alfresco_username": "demo-service-account",
            "alfresco_site": "laboratorio",
            "alfresco_parent_node_id": "",
            "alfresco_target_path": "CIR / Laboratorio / Incidenti",
            "alfresco_verify_tls": "1",
            "alfresco_group_by_type": "1",
            "alfresco_timeout": "30",
        }.items():
            setting(key, value)
        db.session.add(NotificationType(tenant_id=tenant.id, code="documentation-notice",
                                         label="Responsabile · esempio", enabled=True))
        db.session.add(NotificationTemplate(tenant_id=tenant.id, kind="documentation-notice",
                                             name="Notifica dimostrativa", subject="Esempio didattico",
                                             body="Documento per esercitazione, senza invio reale.",
                                             linked_form_template_name=template, action_label_id=labels[3].id,
                                             recipient_source="manual", recipient_value="responsabile@example.invalid"))
        descriptions = [
            "Presa in carico\nRegistrare la conoscenza iniziale e le informazioni disponibili.",
            "Conservazione delle evidenze\nDescrivere le operazioni effettuate per conservare i riscontri tecnici.",
            "Valutazione e documentazione\nRiepilogare la valutazione e predisporre il documento.",
            "Comunicazione al responsabile\nVerificare destinatari e allegati prima della notifica prevista.",
        ]
        for index, label in enumerate(labels):
            db.session.add(IncidentWorkflowStep(
                tenant_id=tenant.id, category_id=category.id, action_label_id=label.id,
                position=index + 1, description=descriptions[index], required=True,
                requires_notification=index == 3,
                required_notification_type="documentation-notice" if index == 3 else None,
                document_generation_enabled=index == 2,
                document_template_name=template if index == 2 else None,
                step_type="registration",
            ))
        ensure_workflow_state(tenant.id, category.id, name="Gestione data breach · esempio")
        people = [Person(tenant_id=tenant.id, name=name, email=email)
                  for name, email in [("Operatore A", "operatore-a@example.invalid"),
                                      ("Analista B", "analista-b@example.invalid")]]
        db.session.add_all(people)
        names = ["Esfiltrazione sospetta da server applicativo", "Credenziali compromesse sul portale VPN",
                 "Accesso anomalo al repository", "E-mail di phishing mirato",
                 "Esposizione di una cartella condivisa", "Indisponibilità del servizio di autenticazione"]
        incidents = []
        for index, name in enumerate(names):
            opened = fixture_time - timedelta(days=index)
            incident = Incident(tenant_id=tenant.id, creator_id=users["demo-supervisor"].id,
                                creator_name="Admin operativo", creator_email="demo-supervisor@example.invalid",
                                name=name, reference=f"DEMO-2026-{48-index:04d}",
                                description="Dati sintetici per la documentazione. Nessun incidente o dato personale reale.",
                                severity_id=severity.id, start_date=opened.date(), start_time=opened.time(),
                                status="chiuso" if index in {3, 5} else "aperto", created_at=opened,
                                end_date=(opened + timedelta(hours=3)).date() if index in {3, 5} else None,
                                end_time=(opened + timedelta(hours=3)).time() if index in {3, 5} else None)
            incident.categories = [category]
            incident.category_order = str(category.id)
            incident.people = people if index % 2 == 0 else people[:1]
            db.session.add(incident)
            db.session.flush()
            db.session.add(Action(incident_id=incident.id, when_at=opened, person_name="Operatore A",
                                  description="Presa in carico registrata nell'esercitazione.", label_id=labels[0].id))
            if index in {3, 5}:
                # Complete the real workflow tasks for closed demo cases. A
                # 'chiuso' status alone still leaves warning icons in the list.
                # Delivery to external systems is never performed by fixtures.
                for sequence, task_label in enumerate(labels[1:], 1):
                    db.session.add(Action(incident_id=incident.id,
                                          when_at=opened + timedelta(minutes=sequence * 30),
                                          person_name="Operatore A",
                                          description="Completamento documentato nel caso sintetico.",
                                          label_id=task_label.id))
            incidents.append(incident)
        # Independent, anonymized SPAM exercise based on the supplied workflow.
        # Never import source recipients, internal URLs, personal data or PDF bytes.
        spam = json.loads((Path(__file__).resolve().parents[1] / "tests" / "fixtures" /
                           "spam_training_workflow.json").read_text(encoding="utf-8"))
        assert spam["category"] == "SPAM" and len(spam["steps"]) == 13
        spam_category = ConfigLabel.query.filter_by(
            tenant_id=tenant.id, kind="category", value="SPAM").first()
        if spam_category is None:
            spam_category = ConfigLabel(
                tenant_id=tenant.id, kind="category", value="SPAM",
                description="Accesso non autorizzato alla posta - laboratorio sintetico")
            db.session.add(spam_category)
            db.session.flush()
        # Do not overwrite a pre-existing tenant category or its operational workflow.
        if IncidentWorkflowStep.query.filter_by(
                tenant_id=tenant.id, category_id=spam_category.id).first():
            raise ValueError("SPAM documentation fixture requires an unused workflow category")
        for item in spam["steps"]:
            action_label = ConfigLabel.query.filter_by(tenant_id=tenant.id, kind="action_label",
                                                       value=item["label"]).first()
            if action_label is None:
                action_label = ConfigLabel(tenant_id=tenant.id, kind="action_label", value=item["label"])
                db.session.add(action_label)
                db.session.flush()
            action_label.max_completion_hours = item["max_completion_hours"]
            action_label.automatic_operations = item["automatic_operations"]
            db.session.add(IncidentWorkflowStep(
                tenant_id=tenant.id, category_id=spam_category.id,
                action_label_id=action_label.id, position=item["position"],
                description=item["description"], step_type=item["step_type"],
                conditions=",".join(item["conditions"]), required=item["required"],
                requires_notification=item["requires_notification"],
                required_notification_type=item["required_notification_type"] or None,
                document_generation_enabled=item["document_generation_enabled"],
                document_template_name=item["document_template_name"] or None,
                section_target=item["section_target"] or None))
        ensure_workflow_state(tenant.id, spam_category.id, name="SPAM - laboratorio")
        spam_incident = Incident(tenant_id=tenant.id, creator_id=users["demo-supervisor"].id,
                                creator_name="Admin operativo", creator_email="demo-supervisor@example.invalid",
                                name="SPAM - account dimostrativo", reference="DEMO-SPAM-2026-0001",
                                description="Incidente interamente sintetico, senza indirizzi o persone reali.",
                                severity_id=severity.id, personal_data=True, start_date=fixture_time.date(),
                                start_time=fixture_time.time(), status="aperto", created_at=fixture_time)
        # Fixture reproduces historical duplicated inherited names. The
        # operational selection must collapse them without destructive cleanup.
        for kind, value in (('category', 'SPAM'), ('data_type', 'E-mail didattica')):
            if ConfigLabel.query.filter_by(tenant_id=tenant.id, kind=kind, value=value).first() is None:
                db.session.add(ConfigLabel(tenant_id=tenant.id, kind=kind, value=value, group='laboratorio'))
            alias = value + ' [Tenants Default]'
            if ConfigLabel.query.filter_by(tenant_id=tenant.id, kind=kind, value=alias).first() is None:
                db.session.add(ConfigLabel(tenant_id=tenant.id, kind=kind, value=alias, group='laboratorio'))
        db.session.flush()
        spam_incident.categories = [spam_category]
        spam_incident.category_order = str(spam_category.id)
        db.session.add(spam_incident)
        db.session.flush()
        spam_incident_id = spam_incident.id
        kb = "Procedure dimostrative: registrare le attività con Azioni; allegare le evidenze in Documenti."
        (Path(app.config["AI_CHATBOT_DOC_DIR"]) / "procedure-demo.txt").write_text(kb, encoding="utf-8")
        db.session.add(AIChatbotDocument(tenant_id=tenant.id, title="Procedure dimostrative CIR",
                                         filename="procedure-demo.txt", original_filename="procedure-demo.txt",
                                         content_type="text/plain", size_bytes=len(kb.encode()), extracted_text=kb))
        db.session.commit()
        fixture = {"fixture_id": FIXTURE_ID, "incident_id": incidents[0].id,
                   "incident_reference": incidents[0].reference,
                   "default_tenant_id": tenant.id, "other_tenant_id": other.id,
                   "usernames": list(users), "incident_start_utc": fixture_time.isoformat(),
                   "timestamp_policy": "synthetic start 2h18m before capture, then one day per scenario",
                   "incident_count": len(incidents), "workflow_step_count": 4, "spam_incident_id": spam_incident_id, "spam_workflow_step_count": 13}
    return app, fixture
