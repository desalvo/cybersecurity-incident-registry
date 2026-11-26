"""RC92: the modern incident workflow wraps phase cards rather than scrolling.

This is an interface-only change. The server-side workflow order and operations
must remain unchanged, and connection arrows must follow the actual row geometry.
"""
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / 'app/static/ui/incident.css'
JS = ROOT / 'app/static/ui/incident.js'


def test_modern_workflow_does_not_force_horizontal_scrolling():
    stylesheet = CSS.read_text(encoding='utf-8')
    script = JS.read_text(encoding='utf-8')
    assert 'grid-template-columns:repeat(auto-fit,minmax(min(100%,270px),1fr))' in stylesheet
    assert 'grid-template-columns:minmax(0,1fr)' in stylesheet
    assert 'overflow:visible' in stylesheet
    assert 'workflow-step-card.workflow-connector-wrap' in stylesheet
    assert 'workflow-step-card.workflow-connector-down' in stylesheet
    assert 'workflow-step-card.workflow-connector-right' in stylesheet
    assert 'initWorkflowConnectors();' in script
    assert "grid.querySelectorAll('.workflow-step-card')" in script
    assert 'new ResizeObserver(requestLayout)' in script
    assert 'window.addEventListener(\'resize\', requestLayout)' in script
    assert 'scroll-snap-type:none' in stylesheet


@pytest.mark.parametrize('viewport, columns', [(1400, 4), (1024, 3), (800, 2), (600, 1), (420, 1), (320, 1)])
def test_modern_workflow_cards_wrap_responsively_in_browser(viewport, columns):
    playwright = pytest.importorskip('playwright.sync_api')
    chrome = shutil.which('chromium') or shutil.which('chromium-browser')
    if not chrome:
        pytest.skip('Chromium is not available in this test environment')
    css = (ROOT / 'app/static/style.css').read_text(encoding='utf-8')
    incident_css = CSS.read_text(encoding='utf-8')
    js = JS.read_text(encoding='utf-8')
    cards = []
    for number in range(1, 9):
        cards.append(f'''<div class="workflow-step workflow-step-card">
        <span class="workflow-step-sequence">{number}</span>
        <div class="workflow-step-flow"><p class="cir-workflow-state">Da completare</p>
        <h3 class="cir-workflow-title">Fase {number}</h3><p>Descrizione e condizioni</p></div>
        <div class="workflow-step-task"><p class="workflow-registration-phase">Azione {number}</p>
        <span class="cir-workflow-command">Apri sezione</span></div></div>''')
        if number != 8:
            cards.append('<span class="workflow-step-arrow" aria-hidden="true">→</span>')
    html = f'''<!doctype html><html><head><style>{css}</style><style>{incident_css}</style></head>
    <body class="cir-modern"><div style="max-width:1400px;margin:auto;padding:12px">
    <details open id="incident-workflow" class="incident-section-collapsible"><summary>Fasi procedurali</summary>
    <div class="incident-section-body"><div class="workflow-steps workflow-steps-ordered">{''.join(cards)}
    </div></div></details></div><script>{js}</script></body></html>'''
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=chrome, args=['--no-sandbox'])
        try:
            page = browser.new_page(viewport={'width': viewport, 'height': 960})
            page.set_content(html, wait_until='load')
            page.wait_for_function("document.querySelectorAll('.workflow-connector-right,.workflow-connector-wrap,.workflow-connector-down').length === 7")
            data = page.evaluate('''() => {
              const grid = document.querySelector('.workflow-steps');
              const cards = [...grid.querySelectorAll('.workflow-step-card')];
              return {width:grid.clientWidth, scrollWidth:grid.scrollWidth,
                lefts:cards.map(c=>Math.round(c.getBoundingClientRect().left)),
                tops:cards.map(c=>Math.round(c.getBoundingClientRect().top)),
                widths:cards.map(c=>Math.round(c.getBoundingClientRect().width)),
                dirs:cards.map(c=>c.classList.contains('workflow-connector-right') ? 'right' :
                    c.classList.contains('workflow-connector-wrap') ? 'wrap' :
                    c.classList.contains('workflow-connector-down') ? 'down' : 'none')};
            }''')
        finally:
            browser.close()
    assert data['scrollWidth'] <= data['width'] + 2
    assert len(set(data['lefts'])) == columns
    assert min(data['widths']) >= min(260, data['width'] - 12)
    assert data['dirs'][-1] == 'none'
    for i in range(7):
        direction = ('right' if data['tops'][i] == data['tops'][i+1]
            else 'down' if data['lefts'][i] == data['lefts'][i+1] else 'wrap')
        assert data['dirs'][i] == direction
