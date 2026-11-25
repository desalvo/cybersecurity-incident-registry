#!/usr/bin/env python3
"""Capture documentation from the real CIR application in an isolated browser.

Run from a clean checkout with requirements-ui.txt and its Chromium installed.
There is intentionally no --base-url option: this command cannot point at a
deployed instance. Only a new synthetic SQLite fixture and loopback servers are
used. The application itself is not patched or replaced by static mock HTML.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import traceback
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from release_metadata import resolve_build
from application_identity import read_application_identity
from scripts.seed_ui_documentation import FIXTURE_ID, isolated_environment, seed_documentation_app

PLAYWRIGHT_VERSION = "1.65.2"
DESKTOP = {"width": 1920, "height": 1140}
MOBILE = {"width": 430, "height": 932}
REQUIRED_CAPTURES = {
    "login-desktop", "login-mobile", "registry-desktop", "registry-closed-state", "registry-mobile",
    "registry-mobile-menu", "incident-desktop", "incident-mobile",
    "spam-incident-desktop", "spam-incident-config-labels", "spam-workflow-steps",
    "pdf-mapping-configuration", "pdf-generated-preview", "alfresco-settings-desktop",
    "alfresco-incident-documents",
    "assistant-desktop", "assistant-mobile", "interface-settings-desktop",
    "classic-registry-desktop", "admin-modules-desktop", "admin-sso-desktop",
    "documentation-user-desktop", "documentation-user-mobile",
    "documentation-admin-desktop", "documentation-admin-mobile",
}
DEMO_ANSWER = (
    "Risposta dimostrativa per la documentazione · provider locale di test.\n\n"
    "Per registrare la conservazione delle evidenze:\n"
    "1. Apri Azioni oppure usa Registra azione nel blocco del workflow.\n"
    "2. Seleziona la label prevista e verifica data e operatore.\n"
    "3. Descrivi le operazioni effettuate e aggiungi gli eventuali allegati.\n"
    "4. Salva l'azione. Il completamento dipende dalle condizioni del workflow.\n\n"
    "La registrazione resta sotto il tuo controllo."
)


def source_commit(expected: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", expected or ""):
        raise ValueError("--source-commit must be a full Git SHA")
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if actual != expected:
        raise ValueError("Screenshot source commit does not match the checkout")
    status = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, text=True)
    expected_build = os.environ.get("CIR_RELEASE_BUILD", "")
    if expected_build and (resolve_build(explicit=expected_build) != expected_build
                           or (ROOT / "BUILD").read_text(encoding="utf-8") != expected_build + "\n"):
        raise ValueError("Real screenshot evidence requires a clean source tree with the exact authorized CI BUILD")
    if status.strip():
        # CI derives the build date once, then stamps the same BUILD into every
        # job. This is the sole permitted generated overlay on the source SHA;
        # staged metadata, VERSION edits and any executable changes still fail.
        if status.splitlines() != [" M BUILD"] or not expected_build:
            raise ValueError("Real screenshot evidence requires a clean tracked source tree except the authorized CI BUILD")
    untracked = subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard", "--", "app", "scripts", "requirements-ui.txt", "requirements-docs.txt", "release_metadata.py", "application_identity.py"], cwd=ROOT, text=True).strip()
    if untracked:
        raise ValueError("Untracked executable source is not allowed in screenshot evidence")
    return actual


def prepare_output(path: Path) -> Path:
    path = path.resolve()
    if path == ROOT or any(path.is_relative_to(ROOT / name) for name in ("app", "scripts", "docs", ".github")):
        raise ValueError("Capture output cannot overwrite application or documentation sources")
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise ValueError("Capture output must be a new or empty directory")
    path.mkdir(parents=True, exist_ok=True)
    (path / "screenshots").mkdir()
    return path


@contextmanager
def local_provider():
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if self.path != "/api/chat" or not 0 < length < 500_000:
                    raise ValueError("Unexpected fixture request")
                payload = json.loads(self.rfile.read(length))
                messages = payload.get("messages", [])
                if payload.get("model") != FIXTURE_ID or len(messages) != 2:
                    raise ValueError("Provider contract must contain system context and current question only")
                if [item.get("role") for item in messages] != ["system", "user"]:
                    raise ValueError("Unexpected provider roles")
                calls.append({"roles": [item["role"] for item in messages],
                              "database_snapshot_included": "# Snapshot database applicativo sanitizzato" in messages[0].get("content", "")})
                body = json.dumps({"message": {"role": "assistant", "content": DEMO_ANSWER}}).encode()
                self.send_response(200)
            except (ValueError, TypeError, KeyError):
                body = b'{"error":"Invalid documentation fixture request"}'
                self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/api/chat", calls
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@contextmanager
def serve_application(app):
    from werkzeug.serving import WSGIRequestHandler, make_server

    class QuietHandler(WSGIRequestHandler):
        def log(self, *_args, **_kwargs):
            pass

    server = make_server("127.0.0.1", 0, app, threaded=True, request_handler=QuietHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def validate_capture_set(entries):
    ids = [entry["id"] for entry in entries]
    if len(ids) != len(set(ids)) or set(ids) != REQUIRED_CAPTURES:
        raise ValueError("Incomplete or duplicated documentation screenshots")
    for entry in entries:
        if entry["ui_mode"] not in {"modern", "classic"}:
            raise ValueError("Unexpected screenshot UI mode")
        if not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
            raise ValueError("Missing screenshot hash")


def verify_generated_pdf_final_print(pdf_bytes: bytes, expected_reference: str) -> None:
    """Validate the *flattened* incident PDF, not the editable source template.

    CIR deliberately paints mapped values into the PDF page and removes the
    AcroForm widgets. ``PdfReader.get_fields()`` therefore MUST be empty for a
    generated document. The original template (verified by the fixture) is the
    only artifact where editable AcroForm field names should still exist.
    """
    from io import BytesIO
    from pypdf import PdfReader

    if not pdf_bytes.startswith(b'%PDF-'):
        raise AssertionError('Generated document is not a PDF')
    if not expected_reference:
        raise AssertionError('Missing expected synthetic incident reference')
    reader = PdfReader(BytesIO(pdf_bytes))
    if not reader.pages:
        raise AssertionError('Generated PDF contains no pages')
    fields = reader.get_fields() or {}
    if fields:
        raise AssertionError('Generated PDF still contains editable AcroForm fields')
    for page_index, page in enumerate(reader.pages, start=1):
        for annotation in page.get('/Annots') or []:
            obj = annotation.get_object() if hasattr(annotation, 'get_object') else annotation
            if obj.get('/Subtype') == '/Widget':
                raise AssertionError(f'Generated PDF still has a form widget on page {page_index}')
    rendered = '\n'.join(page.extract_text() or '' for page in reader.pages)
    if expected_reference not in rendered:
        raise AssertionError('Generated PDF does not contain the rendered incident reference')



def capture_browser(app, fixture, base_url, password, output, commit, provider_calls):
    from playwright.sync_api import expect, sync_playwright

    if version("playwright") != PLAYWRIGHT_VERSION:
        raise RuntimeError("Install the exact requirements-ui.txt before capturing")
    errors, blocked, screenshots, checks = [], [], [], {}
    origin = urlparse(base_url).netloc
    identity = read_application_identity(ROOT)

    def context(browser, viewport):
        ctx = browser.new_context(viewport=viewport, locale="it-IT", timezone_id="Europe/Rome",
                                  device_scale_factor=1, reduced_motion="reduce",
                                  is_mobile=viewport == MOBILE, has_touch=viewport == MOBILE,
                                  service_workers="block")

        def only_fixture(route):
            parsed = urlparse(route.request.url)
            if parsed.scheme in {"data", "blob"} or (parsed.scheme == "http" and parsed.netloc == origin):
                route.continue_()
            else:
                blocked.append(parsed.scheme + "://" + parsed.netloc)
                route.abort()
        ctx.route("**/*", only_fixture)
        ctx.set_default_timeout(15_000)
        return ctx

    def new_page(ctx):
        page = ctx.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        return page

    def go(page, route, mode="modern"):
        response = page.goto(base_url + route, wait_until="networkidle")
        assert response is not None and response.status == 200, f"Route failed: {route}"
        assert urlparse(page.url).path == urlparse(route).path, f"Unexpected route redirect: {route}"
        expect(page.locator("body")).to_have_class(re.compile(r"\bcir-" + mode + r"\b"))
        # A same-URL reload can restore the scroll left by a workflow jump.
        # Start the next documented view at its real page header consistently.
        page.evaluate("window.scrollTo({top: 0, left: 0, behavior: 'instant'})")
        return response

    def login(page, username):
        go(page, "/login")
        page.locator('input[name="username"]').fill(username)
        page.locator('input[name="password"]').fill(password)
        page.locator('form:has(input[name="password"]) button[type="submit"], form:has(input[name="password"]) button:not([type])').first.click()
        page.wait_for_url(base_url + "/", wait_until="networkidle")
        expect(page.locator("body")).to_have_class(re.compile(r"\bcir-modern\b"))
        expect(page.locator("#main-content")).to_be_visible()

    def snap(page, capture_id, caption_it, caption_en, authenticated=True, mode="modern", full_page=False, element=None):
        page.evaluate("document.fonts.ready")
        # Playwright's string predicate invokes eval and violates the application's
        # strict CSP. Poll through page.evaluate with a callable instead.
        for _ in range(100):
            if page.evaluate("""() => Array.from(document.images).filter(i => { const r=i.getBoundingClientRect(); return r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth; }).every(i => i.complete)"""):
                break
            page.wait_for_timeout(100)
        else:
            raise AssertionError(f"Images did not finish loading on {capture_id}")
        broken = page.evaluate("""() => Array.from(document.images).filter(i => { const r=i.getBoundingClientRect(); return r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth && (!i.complete || i.naturalWidth === 0); }).map(i => ({src:i.currentSrc || i.src, complete:i.complete, naturalWidth:i.naturalWidth}))""")
        assert not broken, f"Broken visible image on {capture_id}: {broken!r}"
        overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        assert overflow <= 2, f"Page-level horizontal overflow on {capture_id}: {overflow}"
        # JPEG reduces the distributed presentation, PDF and CI artifact sizes.
        # Quality 90 preserves small UI labels and coloured navigation badges.
        # Transparent branding and exact-pixel test fixtures remain PNG.
        filename = f"screenshots/{capture_id}.jpg"
        target = output / filename
        if element is not None:
            element.screenshot(path=str(target), type="jpeg", quality=90,
                               animations="disabled")
        else:
            page.screenshot(path=str(target), type="jpeg", quality=90,
                            full_page=full_page, animations="disabled")
        screenshots.append({"id": capture_id, "file": filename,
                            "image_format": "jpeg", "jpeg_quality": 90,
                            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                            "route": urlparse(page.url).path, "viewport": page.viewport_size,
                            "ui_mode": mode, "authenticated": authenticated,
                            "capture_area": "element" if element is not None else ("full-page" if full_page else "viewport"),
                            "caption_it": caption_it, "caption_en": caption_en})

    def ask(page):
        page.locator("#cir-albot-question").fill("Come registro la conservazione delle evidenze?")
        with page.expect_response(lambda response: urlparse(response.url).path == "/ai-chatbot/widget/ask" and response.request.method == "POST") as response:
            page.locator("#cir-albot-send").click()
        assert response.value.status == 200
        payload = response.value.json()
        assert payload.get("ok") is True and payload.get("answer") == DEMO_ANSWER
        expect(page.locator("#cir-albot-panel")).to_contain_text("provider locale di test")

    def set_mode(page, mode):
        form = page.locator('form:has([name="mode"])')
        form.locator(f'[name="mode"][value="{mode}"]').check()
        form.locator('button[type="submit"]').click()
        page.wait_for_load_state("networkidle")
        expect(page.locator("body")).to_have_class(re.compile(r"\bcir-" + mode + r"\b"))

    def check_documentation_cover(page, title_id):
        cover = page.locator('[data-documentation-cover]')
        expect(cover).to_have_count(1)
        expect(cover.locator('#' + title_id)).to_be_visible()
        expect(cover.locator('.cir-doc-brand')).to_contain_text(identity['name'])
        expect(cover.locator('.cir-doc-brand img')).to_have_attribute('src', '/static/help/app-logo.png')
        expect(cover.locator('.cir-doc-badges')).to_contain_text((ROOT / 'VERSION').read_text().strip())
        expect(cover.locator('.cir-doc-badges')).to_contain_text('Build ' + (ROOT / 'BUILD').read_text().strip())
        expect(cover.locator('.cir-doc-hero-image')).to_be_visible()
        expect(cover.locator('.cir-doc-hero-image')).to_have_attribute('src', '/static/ui/cybersecurity-hero-v2.png')
        expect(cover.locator('.cir-doc-about')).to_contain_text(identity['author'])
        expect(cover.get_by_role('link', name=identity['author_email'], exact=True)).to_have_attribute('href', 'mailto:' + identity['author_email'])
        expect(cover.get_by_role('link', name=identity['project_url'], exact=True)).to_have_attribute('href', identity['project_url'])
        platforms = cover.locator('.cir-doc-platforms')
        expect(platforms.locator('img')).to_have_count(len(identity['platforms']))
        for platform in identity['platforms']:
            link = platforms.get_by_role('link', name=platform['name'], exact=True)
            expect(link).to_have_attribute('href', platform['url'])
            expect(link.locator('img')).to_have_attribute('src', '/static/' + platform['logo'])
        for architecture in identity['architectures']:
            expect(platforms).to_contain_text(architecture)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=os.environ.get("CIR_LOCAL_CHROMIUM") or None)
        browser_version = browser.version
        try:
            desktop = context(browser, DESKTOP)
            page = new_page(desktop)
            go(page, "/login")
            expect(page.locator("#cir-albot-open")).to_have_count(0)
            snap(page, "login-desktop", "Accesso reale · desktop", "Actual login · desktop", False)
            checks["modern_is_fresh_install_default"] = True
            anonymous = context(browser, MOBILE)
            mobile_login = new_page(anonymous)
            go(mobile_login, "/login")
            # The approved mobile login places the full brand and photograph
            # below the form. Include them instead of cutting at the first fold.
            snap(mobile_login, "login-mobile", "Accesso reale · mobile", "Actual login · mobile", False, full_page=True)

            login(page, "demo-supervisor")
            # Closed examples must have no pending workflow tasks: a green
            # check icon, not only a textual 'chiuso' status in the row.
            expect(page.locator('.incident-table .procedure-ok-icon')).to_have_count(2)
            expect(page.locator('.incident-table .procedure-danger-icon')).not_to_have_count(0)
            snap(page, "registry-desktop", "Registro aperti/chiusi, icone procedurali autentiche",
                 "Open and closed incidents with authentic procedural state icons")
            page.locator('.incident-table').scroll_into_view_if_needed()
            snap(page, "registry-closed-state", "Icone di stato a inizio riga: avviso e chiusura completa",
                 "Row leading icons: pending warning and complete closure")
            checks["closed_incidents_have_real_green_workflow_icons"] = True
            expect(page.locator('a[href="/incident/' + str(fixture["incident_id"]) + '"]:visible')).not_to_have_count(0)
            page.locator('a[href="/incident/' + str(fixture["incident_id"]) + '"]:visible').first.click()
            page.wait_for_load_state("networkidle")
            expect(page.locator("#incident-workflow .workflow-step-card")).to_have_count(4)
            expect(page.locator("#incident-workflow .workflow-step-arrow")).to_have_count(3)
            snap(page, "incident-desktop", "Incidente reale di esempio e quattro fasi procedurali", "Actual example incident and four procedural stages")
            checks["four_procedural_blocks_rendered"] = True
            # Real authenticated CIR route with the imported 13-step SPAM workflow.
            go(page, f'/incident/{fixture["spam_incident_id"]}')
            # The source workflow has two personal_data-only steps. The synthetic
            # incident explicitly enables that condition so all 13 are rendered.
            expect(page.locator("#incident-workflow .workflow-step-card")).to_have_count(13)
            expect(page.locator("#incident-workflow .workflow-step-arrow")).to_have_count(12)
            snap(page, "spam-incident-desktop", "Incidente SPAM sintetico: interfaccia CIR autentica",
                 "Synthetic SPAM incident: authentic CIR interface")
            page.locator("#incident-workflow").scroll_into_view_if_needed()
            snap(page, "spam-workflow-steps", "Workflow SPAM: 13 fasi, pulsanti e condizioni",
                 "SPAM workflow: 13 stages, controls and conditions", full_page=True)
            checks["spam_real_13_step_workflow_rendered"] = True
            # Regression for old imported '[Tenants Default]' labels: verify
            # both available palettes represent each logical choice only once.
            # This is a real CIR browser capture, never a retouched screenshot.
            region = page.locator('#incident-main .dnd-layout')
            expect(region).to_be_visible()
            for kind in ('categories', 'data_types'):
                chips = region.locator(f'.palette .chip[data-target="{kind}"]')
                raw = [chip.get_attribute('data-text') or '' for chip in chips.all()]
                keys = [re.sub(r'\s*\[Tenants Default(?:\s+\d+)?\]$', '', text.strip(), flags=re.I).casefold() for text in raw]
                assert len(keys) == len(set(keys)), f'Duplicate {kind} choices rendered by CIR: {raw}'
            expect(region.locator('.palette .chip[data-target="categories"][data-text="SPAM"]')).to_have_count(1)
            expect(region.locator('.palette .chip[data-target="data_types"][data-text="E-mail didattica"]')).to_have_count(1)
            snap(page, "spam-incident-config-labels",
                 "Categorie e dati interessati senza duplicazioni da Tenants Default",
                 "Categories and affected data deduplicated from Tenants Default",
                 element=region)
            checks["tenant_defaults_category_and_data_type_choices_are_unique"] = True
            go(page, f'/incident/{fixture["incident_id"]}')

            task = page.locator("#incident-workflow .workflow-step-action").nth(1)
            task_label = task.get_attribute("data-action-label-id")
            assert task_label
            task.click(position={"x": 12, "y": 12})
            expect(page.locator("#new-action-label-id")).to_have_value(task_label)
            expect(page.locator("#incident-actions")).to_have_attribute("open", "")
            go(page, f'/incident/{fixture["incident_id"]}')
            checks["entire_procedural_task_region_activates_real_action_form"] = True
            # Exercise the migrated external confirmation handler on disposable
            # data. Cancel must prevent the HTTP mutation, not just hide a dialog.
            delete_form = page.locator("form.delete-incident-form")
            section = delete_form.locator("xpath=ancestor::details[1]")
            if section.count() and section.get_attribute("open") is None:
                section.locator(":scope > summary").click()
            delete_requests, dialogs = [], []

            def watch_delete(request):
                if request.method == "POST" and urlparse(request.url).path == f'/incident/{fixture["incident_id"]}/delete':
                    delete_requests.append(True)

            def cancel_delete(dialog):
                dialogs.append(dialog.type)
                dialog.dismiss()

            page.on("request", watch_delete)
            page.once("dialog", cancel_delete)
            delete_form.locator('button[type="submit"]').click()
            assert dialogs == ["confirm"] and not delete_requests
            page.remove_listener("request", watch_delete)
            go(page, f'/incident/{fixture["incident_id"]}')
            expect(page.locator("#incident-workflow .workflow-step-card")).to_have_count(4)
            expect(page.locator("#incident-workflow .workflow-step-arrow")).to_have_count(3)
            checks["cancel_confirmation_prevents_incident_delete_request"] = True
            page.locator("#cir-albot-open").click()
            expect(page.locator("#cir-albot-panel")).to_be_visible()
            ask(page)
            panel_box = page.locator("#cir-albot-panel").bounding_box()
            assert panel_box and abs(panel_box["width"] - 360) <= 2
            snap(page, "assistant-desktop", "AlBot nella pagina reale; risposta del provider locale dimostrativo", "AlBot in the actual app; local demonstration provider response")
            page.locator("#cir-albot-close").click()
            expect(page.locator("#cir-albot-panel")).to_be_hidden()
            expect(page.locator("#cir-albot-open")).to_be_focused()
            page.locator("#cir-albot-open").click()
            expect(page.locator("#cir-albot-panel")).to_contain_text("provider locale di test")
            page.locator("#cir-albot-new-question").click()
            expect(page.locator("#cir-albot-panel")).not_to_contain_text("provider locale di test")
            page.keyboard.press("Escape")
            expect(page.locator("#cir-albot-panel")).to_be_hidden()
            checks["assistant_real_csrf_endpoint_and_local_provider"] = True
            checks["assistant_close_reopen_clear_and_focus"] = True

            # The intermediate layout is a real modal, not a crushed workflow.
            page.set_viewport_size({"width": 1366, "height": 900})
            page.locator("#cir-albot-open").click()
            expect(page.locator("#cir-albot-panel")).to_have_attribute("aria-modal", "true")
            page.keyboard.press("Escape")
            expect(page.locator("#cir-albot-open")).to_be_focused()
            page.set_viewport_size(DESKTOP)
            checks["narrow_desktop_assistant_modal"] = True

            go(page, "/")
            page.locator("[data-tenant-switch-select]").select_option(str(fixture["other_tenant_id"]))
            expect(page.locator("#cir-albot-open")).to_have_count(0)
            page.wait_for_load_state("networkidle")
            expect(page.locator("[data-tenant-switch-select]")).to_have_value(str(fixture["other_tenant_id"]))
            page.locator("[data-tenant-switch-select]").select_option(str(fixture["default_tenant_id"]))
            expect(page.locator("#cir-albot-open")).to_be_visible()
            page.wait_for_load_state("networkidle")
            page.locator("#cir-albot-open").click()
            expect(page.locator("#cir-albot-panel")).not_to_contain_text("provider locale di test")
            page.locator("#cir-albot-close").click()
            checks["real_tenant_switch_and_assistant_scope_reset"] = True

            mobile = context(browser, MOBILE)
            mobile_page = new_page(mobile)
            login(mobile_page, "demo-supervisor")
            snap(mobile_page, "registry-mobile", "Registro incidenti · mobile", "Incident registry · mobile")
            mobile_page.locator("#cir-menu-open").click()
            expect(mobile_page.locator("#cir-sidebar")).to_have_class(re.compile(r"\bopen\b"))
            snap(mobile_page, "registry-mobile-menu", "Menu operativo aperto · mobile", "Open application menu · mobile")
            mobile_page.keyboard.press("Escape")
            expect(mobile_page.locator("#cir-menu-open")).to_be_focused()
            go(mobile_page, f'/incident/{fixture["incident_id"]}')
            snap(mobile_page, "incident-mobile", "Incidente e fasi procedurali · mobile", "Incident and procedural stages · mobile")
            mobile_page.locator("#cir-albot-open").click()
            ask(mobile_page)
            snap(mobile_page, "assistant-mobile", "Conversazione AlBot a tutta larghezza · risposta dimostrativa", "Full-width AlBot conversation · demonstration response")
            mobile_page.locator("#cir-albot-back").click()
            expect(mobile_page.locator("#cir-albot-panel")).to_be_hidden()
            expect(mobile_page.locator("#incident-workflow")).to_be_visible()
            checks["mobile_menu_escape_and_assistant_return"] = True

            # These are normal browser viewports of the live online manual,
            # not rendered mock pages or vertically enlarged pretend devices.
            # Actual full PDF first pages are generated separately for the deck.
            for guide, route, title_id in (
                ('user', '/aiuto', 'doc-title'),
                ('admin', '/aiuto/amministrazione', 'admin-doc-title'),
            ):
                for suffix, guide_page in (('desktop', page), ('mobile', mobile_page)):
                    go(guide_page, route)
                    check_documentation_cover(guide_page, title_id)
                    snap(guide_page, 'documentation-' + guide + '-' + suffix,
                         'Apertura reale del manuale online · ' + guide + ' · ' + suffix,
                         'Actual online manual opening · ' + guide + ' · ' + suffix)
            checks['documentation_covers_show_current_identity_and_local_platform_logos'] = True
            checks['documentation_mobile_first_fold_has_no_horizontal_overflow'] = True

            go(page, "/modules/configuration")
            snap(page, "admin-modules-desktop", "Configurazione reale dei moduli", "Actual document template configuration")
            # Inspect three actual AcroForm mapping controls populated by the
            # disposable database fixture, not a static explanatory graphic.
            go(page, "/modules/configuration?template=documentation-valutazione")
            expect(page.locator(".mapping-row")).to_have_count(3)
            for field, source in (
                ("RIFERIMENTO", "reference"),
                ("DESCRIZIONE", "description"),
                ("DATA_INIZIO", "start_date"),
            ):
                expect(page.locator(f'input[name="map__{field}"]')).to_have_value(source)
            page.locator(".dnd-config-grid").scroll_into_view_if_needed()
            snap(page, "pdf-mapping-configuration",
                 "Configurazione reale dei mapping: campi AcroForm e sorgenti incidente",
                 "Actual PDF mapping controls: AcroForm fields and incident values")
            checks["pdf_acroform_mapping_fields_populated"] = True
            # Produce a real PDF using CIR's own form-generation route and
            # render the application's genuine preview page with its iframe.
            # No static screenshot or synthetic HTML is substituted here.
            go(page, f'/incident/{fixture["incident_id"]}')
            section = page.locator('#incident-forms')
            if section.get_attribute('open') is None:
                section.locator(':scope > summary').click()
            form = section.locator('form.template-card-selection-form')
            expect(form.locator('input[value="documentation-valutazione"]')).to_have_count(1)
            # The actual UI deliberately hides the native checkbox and
            # exposes the containing label as a clickable template card.
            # Click the visible card, exactly as an operator would: calling
            # locator.check() on the transparent input times out because the
            # card title intercepts the pointer event.
            form.locator('label.template-select-card:has(input[value="documentation-valutazione"])').click()
            expect(form.locator('input[value="documentation-valutazione"]')).to_be_checked()
            form.get_by_role('button', name='Genera documenti').click()
            expect(page.locator('.generated-preview-card iframe')).to_have_count(1)
            expect(page.get_by_role('heading', name='Anteprima PDF generati')).to_be_visible()
            preview_url = page.locator('.generated-preview-card iframe').get_attribute('src')
            response = desktop.request.get(base_url + preview_url)
            assert response.status == 200, f"Generated PDF request returned HTTP {response.status}"
            verify_generated_pdf_final_print(response.body(), expected_reference=fixture["incident_reference"])
            page.locator('.pdf-preview-frame').scroll_into_view_if_needed()
            page.wait_for_timeout(900)  # Chromium's built-in PDF plugin paints asynchronously.
            snap(page, 'pdf-generated-preview',
                 "Anteprima reale: PDF AcroForm compilato e salvabile dall'incidente",
                 "Real preview: populated AcroForm PDF from an incident")
            checks["real_filled_pdf_generated_and_previewed"] = True
            go(page, "/alfresco/admin/plugins")
            expect(page.locator('input[name="alfresco_base_url"]')).to_have_value("https://alfresco.example.invalid")
            expect(page.locator('input[name="alfresco_site"]')).to_have_value("laboratorio")
            expect(page.locator('input[name="plugin_alfresco_enabled"]')).to_be_checked()
            snap(page, "alfresco-settings-desktop",
                 "Configurazione Alfresco per tenant, endpoint fittizio e nessuna connessione remota",
                 "Tenant Alfresco settings, fictional endpoint with no remote connection")
            checks["alfresco_fixture_offline_configuration_visible"] = True
            go(page, f'/incident/{fixture["incident_id"]}')
            documents = page.locator("#incident-documents")
            documents.scroll_into_view_if_needed()
            if documents.get_attribute("open") is None:
                documents.locator(":scope > summary").click()
            # An <option> is not a visible page element in Chromium; locating
            # the first text match accidentally selected the hidden option.
            # Verify and operate the visible destination control instead.
            storage = documents.locator('select#document-storage-mode')
            expect(storage).to_be_visible()
            expect(storage.locator('option[value="both"]')).to_have_text('CIR + Alfresco')
            expect(storage.locator('option[value="alfresco"]')).to_have_text('Solo Alfresco')
            storage.select_option('both')
            expect(storage).to_have_value('both')
            expect(documents.get_by_role('button', name='Sync Alfresco')).to_be_visible()
            snap(page, "alfresco-incident-documents",
                 "Scelta documenti dell'incidente: gestione locale e opzioni Alfresco",
                 "Incident document controls: local storage and Alfresco options")
            checks["alfresco_incident_documents_controls_visible"] = True
            go(page, "/admin/sso")
            snap(page, "admin-sso-desktop", "Configurazione SSO fittizia nella pagina reale", "Fictional SSO configuration in the actual settings page")
            go(page, "/admin/interface")
            snap(page, "interface-settings-desktop", "Switch globale dell'interfaccia · super admin", "Global interface switch · super admin")

            # A real tenant administrator must not gain global UI control.
            limited = context(browser, DESKTOP)
            limited_page = new_page(limited)
            login(limited_page, "demo-tenant-admin")
            token = limited_page.locator('meta[name="csrf-token"]').get_attribute("content")
            assert token
            denied = limited.request.post(base_url + "/admin/interface", form={"mode": "classic", "_csrf_token": token})
            assert denied.status == 403, "Tenant administrator changed a global setting"
            denied_get = limited.request.get(base_url + "/admin/interface")
            assert denied_get.status == 403
            checks["tenant_admin_global_switch_forbidden"] = True
            missing_csrf = desktop.request.post(base_url + "/admin/interface", form={"mode": "classic"})
            assert missing_csrf.status == 400
            checks["global_switch_requires_csrf"] = True

            reader = context(browser, DESKTOP)
            reader_page = new_page(reader)
            login(reader_page, "demo-reader")
            go(reader_page, f'/incident/{fixture["incident_id"]}')
            expect(reader_page.locator("#incident-workflow .workflow-step-card")).to_have_count(4)
            expect(reader_page.locator("#cir-incident-register-action")).to_have_count(0)
            expect(reader_page.locator("#new-action-label-id")).to_have_count(0)
            checks["reader_sees_workflow_without_write_form"] = True

            other_reader = context(browser, DESKTOP)
            other_page = new_page(other_reader)
            login(other_page, "demo-reader-alt")
            expect(other_page.locator("#cir-albot-open")).to_have_count(0)
            checks["disabled_tenant_plugin_hidden"] = True

            set_mode(page, "classic")
            go(page, "/", "classic")
            snap(page, "classic-registry-desktop", "Interfaccia classica dopo lo switch globale", "Classic interface after the global switch", mode="classic")
            go(other_page, "/", "classic")
            go(mobile_login, "/login", "classic")
            go(page, "/admin/interface", "classic")
            set_mode(page, "modern")
            go(other_page, "/")
            go(mobile_login, "/login")
            checks["global_switch_applies_to_other_tenants_and_login"] = True
            checks["classic_roundtrip_preserves_registry"] = True

            if errors or blocked:
                raise RuntimeError("Browser errors or external requests: " + json.dumps({"errors": errors, "blocked_origins": blocked}, ensure_ascii=False))
            checks["no_browser_errors_or_external_requests"] = True
            checks["visible_images_loaded_no_page_horizontal_overflow"] = True
            validate_capture_set(screenshots)
            assert provider_calls and all(not call["database_snapshot_included"] for call in provider_calls)
            checks["provider_receives_current_question_only_no_db_snapshot"] = True
        finally:
            browser.close()

    manifest = {
        "schema_version": 1, "source_kind": "real-application-browser",
        "source_commit": commit, "functional_version": (ROOT / "VERSION").read_text().strip(),
        "build": (ROOT / "BUILD").read_text().strip(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_provenance": "isolated-synthetic-fixture", "fixture": fixture,
        "browser": {"name": "chromium", "version": browser_version, "playwright": PLAYWRIGHT_VERSION},
        "ai_response_provenance": "deterministic-local-ollama-compatible-http-fixture",
        "ai_endpoint_exercised": "/ai-chatbot/widget/ask", "provider_request_count": len(provider_calls),
        "application_security": {"authentication": "real-login", "csrf": "enabled",
                                 "database_context": False, "production_data_used": False},
        "checks": checks, "screenshots": screenshots,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args(argv)
    commit = source_commit(args.source_commit)
    output = prepare_output(args.output)
    redactions = []
    try:
        with TemporaryDirectory(prefix="cir-ui-documentation-") as temp:
            with isolated_environment(Path(temp)) as private:
                redactions.extend([private["password"], private["secret"], private["encryption_key"]])
                with local_provider() as (provider, calls):
                    app, fixture = seed_documentation_app(Path(temp), private["password"], provider)
                    with serve_application(app) as base_url:
                        manifest = capture_browser(app, fixture, base_url, private["password"], output, commit, calls)
                    with app.app_context():
                        from app.models import db
                        db.session.remove()
                        db.engine.dispose()
        print(f'Real application screenshots: PASS ({len(manifest["screenshots"])} captures)')
        return 0
    except Exception as exc:
        # Preserve the failing assertion location without exposing Python locals
        # or fixture secrets. Previously bare `assert` produced only the string
        # "AssertionError:" and made the CI artifact unactionable.
        message = f"{type(exc).__name__}: {exc}"
        diagnostic = traceback.format_exc()
        for secret in redactions:
            message = message.replace(secret, "[REDACTED]")
            diagnostic = diagnostic.replace(secret, "[REDACTED]")
        last_captures = sorted(p.stem for p in (output / "screenshots").glob("*.jpg"))
        (output / "failure.json").write_text(json.dumps({
            "status": "FAIL", "source_commit": commit, "error": message,
            "traceback": diagnostic, "completed_capture_ids": last_captures,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("Real application screenshots: FAIL\n" + diagnostic, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
