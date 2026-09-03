from pathlib import Path


def test_no_deprecated_sqlalchemy_query_get_calls():
    root = Path(__file__).parents[1]
    offenders = []
    for base in ('app', 'tests', 'scripts'):
        for path in (root / base).rglob('*.py'):
            text = path.read_text(encoding='utf-8')
            deprecated_call = '.query.' + 'get('  # avoid matching this invariant itself
            if deprecated_call in text:
                offenders.append(str(path.relative_to(root)))
    assert not offenders, f'Deprecated SQLAlchemy Query.get() calls found: {offenders}'
