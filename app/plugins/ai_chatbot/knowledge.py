import os
from pathlib import Path
from flask import current_app
from ...models import AIChatbotDocument
from .database_context import database_context_enabled, sanitized_database_context

PROJECT_FILES = [
    'docs/PROJECT_DESIGN.md',
    'README.md',
    'README_en.md',
    'CHANGELOG.txt',
]
TEMPLATE_DOCS = [
    'app/templates/help.html',
    'app/templates/admin_help.html',
    'app/templates/help_en.html',
    'app/templates/admin_help_en.html',
]


def project_root() -> Path:
    return Path(current_app.root_path).parent


def read_text_file(path: Path, limit=20000):
    try:
        if path.exists() and path.is_file():
            return path.read_text(encoding='utf-8', errors='ignore')[:limit]
    except Exception:
        current_app.logger.exception('Unable to read chatbot knowledge file %s', path)
    return ''


def project_knowledge(max_chars=50000):
    root = project_root()
    chunks = []
    for rel in PROJECT_FILES + TEMPLATE_DOCS:
        text = read_text_file(root / rel)
        if text:
            chunks.append(f"\n--- {rel} ---\n{text}")
    data = '\n'.join(chunks)
    return data[:max_chars]


def uploaded_knowledge(max_chars=50000):
    chunks=[]
    for doc in AIChatbotDocument.query.order_by(AIChatbotDocument.uploaded_at.desc()).limit(20).all():
        text=(doc.extracted_text or '').strip()
        if text:
            chunks.append(f"\n--- Documento caricato: {doc.title} ---\n{text[:10000]}")
    return '\n'.join(chunks)[:max_chars]


def build_system_context():
    database_section = ''
    if database_context_enabled():
        database_section = '\n\n# Snapshot database applicativo sanitizzato\n' + sanitized_database_context()
    return (
        "Sei AlBot, chiamabile anche Alex, l'assistente interno dell'applicazione Cybersecurity Incident Registry. "
        "Rispondi in italiano, in modo operativo e prudente, usando la documentazione e le procedure fornite. "
        "Se una procedura non è documentata, dichiaralo e suggerisci di verificare con un amministratore.\n\n"
        "# Documentazione progettuale e funzionale\n" + project_knowledge() +
        "\n\n# Procedure/documenti caricati nel plugin\n" + uploaded_knowledge() + database_section
    )


def extract_text_from_upload(storage):
    filename=(storage.filename or '').lower()
    raw=storage.read()
    storage.seek(0)
    if filename.endswith(('.txt','.md','.csv','.json','.xml','.html','.htm','.log')):
        return raw.decode('utf-8', errors='ignore')
    # Estrazione minimale e sicura: i binari vengono conservati, ma il testo
    # utile al chatbot deve essere caricato preferibilmente in formati testuali.
    return ''
