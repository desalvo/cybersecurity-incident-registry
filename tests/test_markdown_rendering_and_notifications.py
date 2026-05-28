from app.text_filters import strip_markdown_formatting, workflow_markdown


def test_workflow_markdown_supports_controlled_color_and_size():
    html = str(workflow_markdown('{color:#c00}rosso{/color} {size:14px}testo{/size}'))
    assert 'data-md-color="#c00"' in html
    assert 'data-md-size="14px"' in html
    assert 'style=' not in html
    assert 'rosso' in html
    assert 'testo' in html


def test_workflow_markdown_supports_more_safe_colors_and_sizes():
    html = str(workflow_markdown('{color:rgb(200,0,0)}rosso{/color} {color:hsl(210,80%,40%)}blu{/color} {size:120%}grande{/size} {size:1.2rem}rem{/size}'))
    assert 'data-md-color="rgb(200,0,0)"' in html
    assert 'data-md-color="hsl(210,80%,40%)"' in html
    assert 'data-md-size="120%"' in html
    assert 'data-md-size="1.2rem"' in html
    assert 'style=' not in html


def test_workflow_markdown_rejects_unsafe_style_values():
    html = str(workflow_markdown('{color:expression(alert(1))}x{/color} {size:url(js)}y{/size}'))
    assert 'expression' not in html
    assert 'url(js)' not in html
    assert '<span' not in html
    assert 'x' in html and 'y' in html


def test_strip_markdown_formatting_for_scheduled_notifications():
    text = strip_markdown_formatting(
        '# Titolo\n'
        '**Grassetto** e *corsivo* con `codice`\n'
        '{color:red}rosso{/color} {size:18px}grande{/size}\n'
        '[link](https://example.org)'
    )
    assert '# Titolo' not in text
    assert 'Titolo' in text
    assert '**' not in text
    assert '*' not in text
    assert '`' not in text
    assert '{color:' not in text
    assert '{size:' not in text
    assert 'Grassetto' in text
    assert 'corsivo' in text
    assert 'rosso' in text
    assert 'grande' in text
    assert 'link (https://example.org)' in text


def test_markdown_buttons_support_absolute_relative_and_anchor_targets():
    html = str(workflow_markdown(
        '{button:Esterno|https://example.org/run} '
        '{button:Dati generali|#incident-main} '
        '{button:Guida|/help#cap-markdown-rendering} '
        '{button:Query|?open=incident#incident-actions}'
    ))
    assert '<a class="workflow-button-link safe-markdown-button" href="https://example.org/run" target="_blank" rel="noopener noreferrer">Esterno</a>' in html
    assert '<a class="workflow-button-link safe-markdown-button" href="#incident-main">Dati generali</a>' in html
    assert '<a class="workflow-button-link safe-markdown-button" href="/help#cap-markdown-rendering">Guida</a>' in html
    assert '<a class="workflow-button-link safe-markdown-button" href="?open=incident#incident-actions">Query</a>' in html


def test_markdown_buttons_reject_unsafe_targets():
    html = str(workflow_markdown('{button:Male|javascript:alert(1)} {button:Data|data:text/html,x} {button:Proto|//evil.example/x}'))
    assert '<a class="workflow-button-link' not in html
    assert 'javascript:' not in html
    assert 'data:text' not in html
    assert '//evil.example' not in html
    assert 'Male' in html and 'Data' in html and 'Proto' in html


def test_strip_markdown_formatting_handles_relative_buttons():
    text = strip_markdown_formatting('{button:Dati generali|#incident-main} e {button:Guida|/help#cap-markdown-rendering}')
    assert 'Dati generali (#incident-main)' in text
    assert 'Guida (/help#cap-markdown-rendering)' in text
