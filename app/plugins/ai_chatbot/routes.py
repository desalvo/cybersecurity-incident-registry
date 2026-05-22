import json, os, uuid
from pathlib import Path
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from ...models import db, Setting, AIChatbotDocument
from ...routes import audit_log, setting_value, set_setting_value
from .knowledge import build_system_context, extract_text_from_upload
from .database_context import database_context_enabled
from .engines import get_engine, AIEngineError, ENGINE_CLASSES

bp = Blueprint('ai_chatbot', __name__, url_prefix='/ai-chatbot', template_folder='templates')

PLUGIN_CODE = 'ai_chatbot'
ENGINE_NAMES = ['chatgpt', 'claude', 'gemini', 'ollama', 'perplexity']


def _get_setting(key, default=''):
    return setting_value(key, default)


def is_enabled():
    try:
        return _get_setting('plugin_ai_chatbot_enabled', '0') == '1'
    except Exception:
        return False


def admin_required():
    return getattr(current_user, 'is_authenticated', False) and getattr(current_user, 'role', None) == 'admin'


def plugin_config():
    engine = _get_setting('ai_chatbot_engine', 'chatgpt') or 'chatgpt'
    configs = {}
    for name in ENGINE_NAMES:
        configs[name] = {
            'api_key': _get_setting(f'ai_chatbot_{name}_api_key', ''),
            'endpoint': _get_setting(f'ai_chatbot_{name}_endpoint', ''),
            'model': _get_setting(f'ai_chatbot_{name}_model', ''),
        }
    return {'enabled': is_enabled(), 'engine': engine, 'configs': configs, 'include_database_context': database_context_enabled()}


def docs_dir():
    path = Path(current_app.config.get('AI_CHATBOT_DOC_DIR') or os.getenv('AI_CHATBOT_DOC_DIR','/data/ai_chatbot_docs'))
    path.mkdir(parents=True, exist_ok=True)
    return path


@bp.route('', methods=['GET','POST'])
@login_required
def chat():
    if not is_enabled():
        flash('Plugin AI Chatbot non attivo.', 'warning')
        return redirect(url_for('main.index'))
    answer = ''
    question = ''
    if request.method == 'POST':
        question = (request.form.get('question') or '').strip()
        if not question:
            flash('Inserire una domanda per il chatbot.', 'danger')
        else:
            cfg = plugin_config()
            try:
                engine = get_engine(cfg['engine'], cfg['configs'].get(cfg['engine'], {}))
                answer = engine.generate([{'role':'user','content':question}], build_system_context())
                audit_log('ai_chatbot:question', {'engine': cfg['engine'], 'question': question[:300], 'database_context': cfg.get('include_database_context')}, actor_type='user')
                db.session.commit()
            except AIEngineError as exc:
                answer = f'Configurazione o motore AI non disponibile: {exc}'
                audit_log('ai_chatbot:error', {'engine': cfg['engine'], 'error': str(exc)[:500]}, actor_type='user')
                db.session.commit()
            except Exception as exc:
                current_app.logger.exception('AI Chatbot failed')
                answer = 'Errore durante la generazione della risposta del chatbot.'
                audit_log('ai_chatbot:error', {'engine': cfg.get('engine'), 'error': str(exc)[:500]}, actor_type='user')
                db.session.commit()
    return render_template('ai_chatbot_chat.html', question=question, answer=answer, engine=plugin_config()['engine'])


@bp.route('/admin/plugins', methods=['GET','POST'])
@login_required
def admin_plugins():
    if not admin_required():
        flash('Accesso riservato agli amministratori.', 'danger')
        return redirect(url_for('main.index'))
    if request.method == 'POST':
        set_setting_value('plugin_ai_chatbot_enabled', '1' if request.form.get('plugin_ai_chatbot_enabled') == '1' else '0')
        engine = request.form.get('ai_chatbot_engine') or 'chatgpt'
        if engine not in ENGINE_NAMES:
            engine = 'chatgpt'
        set_setting_value('ai_chatbot_engine', engine)
        set_setting_value('ai_chatbot_include_database_context', '1' if request.form.get('ai_chatbot_include_database_context') == '1' else '0')
        for name in ENGINE_NAMES:
            for field in ('api_key','endpoint','model'):
                set_setting_value(f'ai_chatbot_{name}_{field}', request.form.get(f'{name}_{field}') or '')
        audit_log('ai_chatbot:plugin_config_update', {'enabled': request.form.get('plugin_ai_chatbot_enabled') == '1', 'engine': engine, 'database_context': request.form.get('ai_chatbot_include_database_context') == '1'}, actor_type='user')
        db.session.commit()
        flash('Configurazione plugin aggiornata.', 'success')
        return redirect(url_for('ai_chatbot.admin_plugins'))
    return render_template('ai_chatbot_admin_plugins.html', config=plugin_config(), engines=ENGINE_NAMES)


@bp.route('/admin/documents', methods=['GET','POST'])
@login_required
def admin_documents():
    if not admin_required():
        flash('Accesso riservato agli amministratori.', 'danger')
        return redirect(url_for('main.index'))
    if request.method == 'POST':
        upload = request.files.get('document')
        title = (request.form.get('title') or '').strip()
        if not upload or not upload.filename:
            flash('Selezionare un documento da caricare.', 'danger')
        else:
            original = secure_filename(upload.filename)
            stored = f'{uuid.uuid4().hex}_{original}'
            path = docs_dir() / stored
            text = extract_text_from_upload(upload)
            upload.save(path)
            doc = AIChatbotDocument(
                title=title or original,
                filename=stored,
                original_filename=original,
                content_type=upload.mimetype or '',
                size_bytes=path.stat().st_size if path.exists() else 0,
                extracted_text=text,
                uploaded_by_id=getattr(current_user, 'id', None),
            )
            db.session.add(doc)
            audit_log('ai_chatbot:document_upload', {'title': doc.title, 'filename': original}, actor_type='user')
            db.session.commit()
            flash('Documento caricato nella knowledge base del chatbot.', 'success')
        return redirect(url_for('ai_chatbot.admin_documents'))
    docs = AIChatbotDocument.query.order_by(AIChatbotDocument.uploaded_at.desc()).all()
    return render_template('ai_chatbot_admin_documents.html', docs=docs, enabled=is_enabled())


@bp.route('/admin/documents/<int:doc_id>/delete', methods=['POST'])
@login_required
def admin_document_delete(doc_id):
    if not admin_required():
        flash('Accesso riservato agli amministratori.', 'danger')
        return redirect(url_for('main.index'))
    doc = AIChatbotDocument.query.get_or_404(doc_id)
    try:
        (docs_dir() / doc.filename).unlink(missing_ok=True)
    except Exception:
        current_app.logger.exception('Unable to delete AI chatbot document file')
    audit_log('ai_chatbot:document_delete', {'title': doc.title, 'filename': doc.original_filename}, actor_type='user')
    db.session.delete(doc)
    db.session.commit()
    flash('Documento rimosso dalla knowledge base del chatbot.', 'success')
    return redirect(url_for('ai_chatbot.admin_documents'))
