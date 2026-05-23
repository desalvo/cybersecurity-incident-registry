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
