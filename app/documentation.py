"""Authenticated, read-only documentation with one shared About/cover identity."""
from __future__ import annotations

import io
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlsplit

from flask import Blueprint, abort, current_app, g, has_request_context, render_template, request, send_file, url_for
from flask_login import login_required
from markupsafe import Markup, escape

bp = Blueprint('documentation', __name__, url_prefix='/aiuto/guide')
GUIDES = {
    'installation': ('DEPLOYMENT.md', 'Installazione', 'Installation', 'Container, Kubernetes e OpenShift', 'Containers, Kubernetes and OpenShift'),
    'migration': ('MIGRATION.md', 'Migrazione e backup', 'Migration and backup', 'Aggiornamento, ripristino e continuità dei dati', 'Upgrades, recovery and data continuity'),
    'alfresco': ('ADMIN_ALFRESCO.md', 'Guida Alfresco', 'Alfresco guide', 'Documenti e integrazione per tenant', 'Documents and integration per tenant'),
    'security': ('SECURITY.md', 'Sicurezza', 'Security', 'Controlli, vulnerabilità e ciclo di vita', 'Controls, vulnerabilities and lifecycle'),
    'training': ('TRAINING.md', 'Formazione', 'Training', 'Laboratorio operativo sugli incidenti', 'Hands-on incident management'),
    'testing': ('TESTING_AND_PRODUCTION.md', 'Test e produzione', 'Testing and production', 'Verifiche, CI e promozione delle immagini', 'Verification, CI and image promotion'),
    'architecture': ('PROJECT_DESIGN.md', 'Architettura', 'Architecture', 'Modello applicativo e scelte tecniche', 'Application model and technical decisions'),
    'environment': ('CONTAINER_ENVIRONMENT.md', 'Ambiente container', 'Container environment', 'Variabili, configurazione e integrazioni', 'Variables, configuration and integrations'),
    'history': ('DEVELOPMENT_HISTORY.md', 'Storia dello sviluppo', 'Development history', 'Evoluzione tecnica e revisioni', 'Technical evolution and reviews'),
    'release': ('RELEASE.md', 'Procedure di rilascio', 'Release procedures', 'Release candidate, gate e promozione', 'Release candidates, gates and promotion'),
}
_ENDPOINTS = {
    'main.help_page': 'user', 'main.help_pdf': 'user',
    'main.admin_help_page': 'admin', 'main.admin_help_pdf': 'admin',
    'main.release_notes': 'notes', 'main.release_notes_pdf': 'notes',
}


@bp.before_request
def enforce_existing_session_policy():
    # Keep language, inactivity, MFA and disabled-user rules identical to the
    # existing help routes; login_required alone does not enforce them all.
    from .routes import block_disabled
    return block_disabled()


def documentation_context():
    english = getattr(g, 'lang', 'it') == 'en'
    slug = (request.view_args or {}).get('slug') if request.blueprint == 'documentation' else None
    active = slug or _ENDPOINTS.get(request.endpoint)
    if not active:
        return {'cir_documentation_view': False}
    nav = [
        {'id': 'user', 'title': 'User manual' if english else 'Manuale utente', 'url': url_for('main.help_page')},
        {'id': 'admin', 'title': 'Administrator manual' if english else 'Manuale amministratore', 'url': url_for('main.admin_help_page')},
    ]
    nav.extend({'id': key, 'title': item[2 if english else 1], 'url': url_for('documentation.guide', slug=key)}
               for key, item in GUIDES.items())
    nav.append({'id': 'notes', 'title': 'Release notes' if english else 'Note di rilascio', 'url': url_for('main.release_notes')})
    if active in GUIDES:
        item = GUIDES[active]
        title, subtitle = item[2 if english else 1], item[4 if english else 3]
        pdf_url, index = url_for('documentation.guide_pdf', slug=active), '#guide-content'
    elif active == 'admin':
        title = 'Administrator manual' if english else 'Manuale amministratore'
        subtitle = 'Application configuration and management' if english else 'Configurazione e gestione dell’applicazione'
        pdf_url, index = url_for('main.admin_help_pdf'), '#indice-admin'
    elif active == 'notes':
        title, subtitle = ('Release notes', 'Release history and upgrade instructions') if english else ('Note di rilascio', 'Cronologia e istruzioni di aggiornamento')
        pdf_url, index = url_for('main.release_notes_pdf'), '#release-history'
    else:
        title, subtitle = ('User manual', 'Cybersecurity incident management') if english else ('Manuale utente', 'Gestione degli incidenti di sicurezza')
        pdf_url, index = url_for('main.help_pdf'), '#indice'
    return {
        'cir_documentation_view': True, 'cir_documentation_navigation': nav,
        'cir_doc': {'id': active, 'title': title, 'subtitle': subtitle,
                    'pdf_url': pdf_url, 'index': index,
                    'title_id': 'admin-doc-title' if active == 'admin' else 'doc-title'},
    }


def draw_runtime_cover(canvas, document):
    """Use the same native cover on authenticated runtime PDF downloads."""
    if document.page != 1:
        return False
    from scripts.documentation_cover import draw_documentation_cover
    cover = documentation_context()['cir_doc']
    draw_documentation_cover(
        canvas, root=Path(current_app.root_path).parent,
        title=cover['title'], subtitle=cover['subtitle'],
        language=getattr(g, 'lang', 'it'), identity=current_app.config['APP_INFO'],
    )
    return True


def runtime_pdf_visuals(legacy_visuals):
    """Modern PDF screenshots must come from installed, verified CI evidence."""
    from .ui_settings import global_ui_mode
    if global_ui_mode() != 'modern':
        return legacy_visuals
    from .ui_documentation import documentation_screenshot
    result = {}
    mappings = {
        'screenshot-dashboard.png': 'registry-desktop',
        'screenshot-incident-detail.png': 'incident-desktop',
        'screenshot-modules.png': 'admin-modules-desktop',
        'admin-screenshot-modules.png': 'admin-modules-desktop',
        'admin-screenshot-sso.png': 'admin-sso-desktop',
    }
    titles = {
        'registry-desktop': ('Registro incidenti', 'Incident registry'),
        'incident-desktop': ('Dettaglio incidente', 'Incident detail'),
        'admin-modules-desktop': ('Moduli e template', 'Forms and templates'),
        'admin-sso-desktop': ('Configurazione SSO', 'SSO configuration'),
    }
    english = getattr(g, 'lang', 'it') == 'en'
    for chapter, rows in legacy_visuals.items():
        result[chapter] = []
        for label, path in rows:
            if 'screenshot' not in path.name:
                result[chapter].append((label, path))
                continue
            shot = mappings.get(path.name)
            if shot and documentation_screenshot(shot):
                caption = titles[shot][1 if english else 0] + ' — ' + (
                    'Real CI screenshot; isolated synthetic data.' if english
                    else 'Screenshot reale CI; dati dimostrativi isolati.')
                result[chapter].append((caption, Path(current_app.static_folder) / 'help/ui-runtime' / (shot + '.png')))
    return result


def _inline(text):
    """Small Markdown subset; raw HTML and unsafe links remain escaped."""
    escaped = str(escape(text))
    escaped = re.sub(r'`([^`]+)`', r'<code>\1</code>', escaped)
    escaped = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', escaped)
    def link(match):
        label, target = match.groups()
        try:
            parsed = urlsplit(target)
        except ValueError:
            return label + ' (' + target + ')'
        if parsed.scheme in {'http', 'https'} and parsed.hostname:
            return f'<a href="{target}" rel="noopener noreferrer">{label}</a>'
        if not parsed.scheme and not parsed.netloc and has_request_context():
            filename = Path(parsed.path).name
            destination = next((key for key, item in GUIDES.items() if item[0] == filename), None)
            if destination:
                url = url_for('documentation.guide', slug=destination)
                if parsed.fragment:
                    url += '#' + parsed.fragment
                return f'<a href="{escape(url)}">{label}</a>'
            if not parsed.path and re.fullmatch(r'[\w-]+', parsed.fragment):
                return f'<a href="#{parsed.fragment}">{label}</a>'
        return label + ' (' + target + ')'
    return re.sub(r'\[([^\]]+)\]\(([^\s)]+)\)', link, escaped)


def render_source_markdown(text):
    """Render shipped source text without executing HTML, templates or links."""
    html, paragraph, code = [], [], None
    list_open = False
    def flush():
        if paragraph:
            html.append('<p>' + _inline(' '.join(paragraph)) + '</p>')
            paragraph.clear()
    lines = text.splitlines()
    cursor = 0
    while cursor < len(lines):
        line = lines[cursor]
        cursor += 1
        if line.startswith('```'):
            flush()
            if list_open:
                html.append('</ul>'); list_open = False
            if code is None:
                code = []
            else:
                html.append('<pre><code>' + str(escape('\n'.join(code))) + '</code></pre>'); code = None
            continue
        if code is not None:
            code.append(line); continue
        if (line.strip().startswith('|') and cursor < len(lines)
                and re.fullmatch(r'\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*', lines[cursor])):
            flush()
            if list_open:
                html.append('</ul>'); list_open = False
            headers = line.strip().strip('|').split('|')
            html.append('<div class="cir-doc-table-scroll"><table class="table"><thead><tr>' + ''.join('<th>' + _inline(cell.strip()) + '</th>' for cell in headers) + '</tr></thead><tbody>')
            cursor += 1
            while cursor < len(lines) and lines[cursor].strip().startswith('|'):
                cells = lines[cursor].strip().strip('|').split('|')
                html.append('<tr>' + ''.join('<td>' + _inline(cell.strip()) + '</td>' for cell in cells) + '</tr>')
                cursor += 1
            html.append('</tbody></table></div>')
            continue
        heading = re.match(r'^(#{1,6})\s+(.+)', line)
        bullet = re.match(r'^\s*(?:[-*]|\d+[.)])\s+(.+)', line)
        if not line.strip() or heading or bullet:
            flush()
        if list_open and not bullet:
            html.append('</ul>'); list_open = False
        if heading:
            level = min(6, len(heading[1]) + 1)
            identifier = re.sub(r'[^\w\s-]', '', unicodedata.normalize('NFC', heading[2]).lower())
            identifier = re.sub(r'\s+', '-', identifier)
            html.append(f'<h{level} id="{identifier}">{_inline(heading[2])}</h{level}>')
        elif bullet:
            if not list_open:html.append('<ul>'); list_open = True
            html.append('<li>' + _inline(bullet[1]) + '</li>')
        elif line.strip() == '---':
            html.append('<hr>')
        elif line.strip():
            paragraph.append(line)
    flush()
    if list_open:html.append('</ul>')
    if code is not None:html.append('<pre><code>' + str(escape('\n'.join(code))) + '</code></pre>')
    return Markup('\n'.join(html))  # nosec B704: every source fragment is escaped above


def _source(slug):
    item = GUIDES.get(slug)
    if item is None:abort(404)
    path = Path(current_app.root_path).parent / 'docs' / item[0]
    if not path.is_file() or path.is_symlink():abort(404)
    return path.read_text(encoding='utf-8')


@bp.route('/<slug>')
@login_required
def guide(slug):
    return render_template('documentation/guide.html', guide_body=render_source_markdown(_source(slug)))


@bp.route('/<slug>/pdf')
@login_required
def guide_pdf(slug):
    from scripts.documentation_markdown_pdf import build_markdown_pdf
    text = _source(slug)
    cover = documentation_context()['cir_doc']
    output = io.BytesIO()
    build_markdown_pdf(output, text, root=Path(current_app.root_path).parent,
                       title=cover['title'], subtitle=cover['subtitle'],
                       language=getattr(g, 'lang', 'it'), identity=current_app.config['APP_INFO'])
    output.seek(0)
    return send_file(output, mimetype='application/pdf', as_attachment=True,
                     download_name=f'cybersecurity-incident-registry-{slug}.pdf')
