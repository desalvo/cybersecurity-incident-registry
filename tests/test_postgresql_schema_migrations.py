from pathlib import Path


def test_description_required_uses_postgresql_boolean_default():
    source = Path('app/__init__.py').read_text()
    assert 'description_required BOOLEAN DEFAULT FALSE NOT NULL' in source
    assert 'description_required BOOLEAN DEFAULT 0 NOT NULL' not in source
