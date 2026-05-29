import json, os, uuid
from pathlib import Path
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from ...models import db, Setting, AIChatbotDocument
from ...routes import audit_log, setting_value, set_setting_value, validate_upload_file
from .knowledge import build_system_context, extract_text_from_upload
from .database_context import database_context_enabled
from .engines import get_engine, AIEngineError, ENGINE_CLASSES
from .security import validate_ai_endpoint

bp = Blueprint('ai_chatbot', __name__, url_prefix='/ai-chatbot', template_folder='templates')

PLUGIN_CODE = 'ai_chatbot'
ENGINE_NAMES = ['chatgpt', 'claude', 'gemini', 'ollama', 'perplexity']
ENGINE_LABELS = {
    'chatgpt': 'ChatGPT',
    'claude': 'Claude',
    'gemini': 'Gemini',
    'ollama': 'Ollama',
    'perplexity': 'Perplexity',
}
DEFAULT_BACKEND_CONFIGS = {
    'chatgpt': {'api_key': '', 'endpoint': '', 'model': 'gpt-4o-mini'},
    'claude': {'api_key': '', 'endpoint': '', 'model': 'claude-3-5-sonnet-latest'},
    'gemini': {'api_key': '', 'endpoint': '', 'model': 'gemini-1.5-flash'},
    'ollama': {'api_key': '', 'endpoint': 'http://localhost:11434/api/chat', 'model': 'llama3.1'},
    'perplexity': {'api_key': '', 'endpoint': '', 'model': 'sonar'},
}


def _get_setting(key, default=''):
    return setting_value(key, default)


def is_enabled():
    try:
        return _get_setting('plugin_ai_chatbot_enabled', '0') == '1'
    except Exception:
        return False


def admin_required():
    return getattr(current_user, 'is_authenticated', False) and getattr(current_user, 'role', None) in ['admin','superuser']


def _mask_secret(value):
    """Return a non-reversible display mask for stored API keys.

    The admin UI must show that a key is present without exposing the
    secret.  Only the last four characters are shown to help operators
    distinguish rotated keys; the real value is never rendered in HTML.
    """
    value = (value or '').strip()
    if not value:
        return ''
    suffix = value[-4:] if len(value) >= 4 else '****'
    return f'••••••••{suffix}'


def plugin_config():
    engine = _get_setting('ai_chatbot_engine', 'chatgpt') or 'chatgpt'
    configs = {}
    for name in ENGINE_NAMES:
        defaults = DEFAULT_BACKEND_CONFIGS.get(name, {})
        api_key = _get_setting(f'ai_chatbot_{name}_api_key', defaults.get('api_key', ''))
        configs[name] = {
            'api_key': api_key,
            'has_api_key': bool(api_key),
            'masked_api_key': _mask_secret(api_key),
            'endpoint': _get_setting(f'ai_chatbot_{name}_endpoint', defaults.get('endpoint', '')),
            'model': _get_setting(f'ai_chatbot_{name}_model', defaults.get('model', '')),
            'label': ENGINE_LABELS.get(name, name.capitalize()),
        }
    return {
        'enabled': is_enabled(),
        'engine': engine,
        'configs': configs,
        'include_database_context': database_context_enabled(),
        'engine_labels': ENGINE_LABELS,
    }


def reset_single_backend_defaults(name):
    """Restore one AI backend/motor configuration to application defaults.

    Only endpoint, model and API key for the selected backend are reset.  The
    active engine, plugin enablement and database-context option are intentionally
    left unchanged.
    """
    if name not in ENGINE_NAMES:
        raise ValueError('Motore AI non valido.')
    defaults = DEFAULT_BACKEND_CONFIGS[name]
    for field in ('api_key', 'endpoint', 'model'):
        set_setting_value(f'ai_chatbot_{name}_{field}', defaults[field])


def reset_backend_defaults():
    """Restore all AI backend settings to application defaults.

    This intentionally resets only backend-related settings: active engine,
    endpoint, model and API key for every supported provider.  Plugin enablement
    and the database-context option are left unchanged because they are global
    plugin settings, not backend credentials or backend connection details.
    """
    set_setting_value('ai_chatbot_engine', 'chatgpt')
    for name in ENGINE_NAMES:
        reset_single_backend_defaults(name)


def docs_dir():
    path = Path(current_app.config.get('AI_CHATBOT_DOC_DIR') or os.getenv('AI_CHATBOT_DOC_DIR','/data/ai_chatbot_docs'))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _generate_chatbot_answer(question):
    """Generate an AI Chatbot answer for both the full page and the floating widget."""
    cfg = plugin_config()
    engine = get_engine(cfg['engine'], cfg['configs'].get(cfg['engine'], {}))
    answer = engine.generate([{'role': 'user', 'content': question}], build_system_context())
    audit_log('ai_chatbot:question', {
        'engine': cfg['engine'],
        'question': question[:300],
        'database_context': cfg.get('include_database_context')
    }, actor_type='user')
    db.session.commit()
    return answer, cfg['engine']


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
                answer, _engine_name = _generate_chatbot_answer(question)
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


@bp.route('/widget/ask', methods=['POST'])
@login_required
def widget_ask():
    """AJAX endpoint used by the global floating chatbot widget."""
    if not is_enabled():
        return jsonify({'ok': False, 'error': 'Plugin AI Chatbot non attivo.'}), 403
    payload = request.get_json(silent=True) or {}
    question = (payload.get('question') or request.form.get('question') or '').strip()
    if not question:
        return jsonify({'ok': False, 'error': 'Inserire una domanda per il chatbot.'}), 400
    cfg = plugin_config()
    try:
        answer, engine_name = _generate_chatbot_answer(question)
        return jsonify({'ok': True, 'answer': answer, 'engine': engine_name})
    except AIEngineError as exc:
        audit_log('ai_chatbot:error', {'engine': cfg.get('engine'), 'error': str(exc)[:500], 'source': 'widget'}, actor_type='user')
        db.session.commit()
        return jsonify({'ok': False, 'error': f'Configurazione o motore AI non disponibile: {exc}'}), 503
    except Exception as exc:
        current_app.logger.exception('AI Chatbot widget failed')
        audit_log('ai_chatbot:error', {'engine': cfg.get('engine'), 'error': str(exc)[:500], 'source': 'widget'}, actor_type='user')
        db.session.commit()
        return jsonify({'ok': False, 'error': 'Errore durante la generazione della risposta del chatbot.'}), 500


@bp.route('/admin/plugins', methods=['GET','POST'])
@login_required
def admin_plugins():
    if not admin_required():
        flash('Accesso riservato agli amministratori.', 'danger')
        return redirect(url_for('main.index'))
    if request.method == 'POST':
        action = request.form.get('action') or 'save'
        if action == 'reset_backend_defaults':
            reset_backend_defaults()
            audit_log('ai_chatbot:backend_config_reset', {
                'engine': 'chatgpt',
                'backends': ENGINE_NAMES,
            }, actor_type='user')
            db.session.commit()
            flash('Configurazioni dei backend AI ripristinate ai valori di default.', 'success')
            return redirect(url_for('ai_chatbot.admin_plugins'))
        if action.startswith('reset_backend_defaults:'):
            backend_name = action.split(':', 1)[1]
            try:
                reset_single_backend_defaults(backend_name)
            except ValueError as exc:
                flash(str(exc), 'danger')
                return redirect(url_for('ai_chatbot.admin_plugins'))
            audit_log('ai_chatbot:single_backend_config_reset', {
                'backend': backend_name,
                'label': ENGINE_LABELS.get(backend_name, backend_name),
            }, actor_type='user')
            db.session.commit()
            flash(f'Configurazione del backend {ENGINE_LABELS.get(backend_name, backend_name)} ripristinata ai valori di default.', 'success')
            return redirect(url_for('ai_chatbot.admin_plugins'))

        set_setting_value('plugin_ai_chatbot_enabled', '1' if request.form.get('plugin_ai_chatbot_enabled') == '1' else '0')
        engine = request.form.get('ai_chatbot_engine') or 'chatgpt'
        if engine not in ENGINE_NAMES:
            engine = 'chatgpt'
        set_setting_value('ai_chatbot_engine', engine)
        set_setting_value('ai_chatbot_include_database_context', '1' if request.form.get('ai_chatbot_include_database_context') == '1' else '0')
        try:
            api_key_updates = []
            for name in ENGINE_NAMES:
                for field in ('api_key','endpoint','model'):
                    value = request.form.get(f'{name}_{field}') or ''
                    if field == 'api_key':
                        # Empty API key fields mean "keep the current secret".
                        # Stored keys are never sent back to the browser; admins can
                        # only replace them by typing a new value.
                        if value.strip():
                            set_setting_value(f'ai_chatbot_{name}_{field}', value.strip())
                            api_key_updates.append(name)
                        continue
                    if field == 'endpoint':
                        value = validate_ai_endpoint(value, name)
                    set_setting_value(f'ai_chatbot_{name}_{field}', value)
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'danger')
            return redirect(url_for('ai_chatbot.admin_plugins'))
        audit_log('ai_chatbot:plugin_config_update', {
            'enabled': request.form.get('plugin_ai_chatbot_enabled') == '1',
            'engine': engine,
            'database_context': request.form.get('ai_chatbot_include_database_context') == '1',
            'api_keys_overwritten': api_key_updates,
        }, actor_type='user')
        db.session.commit()
        flash('Configurazione plugin aggiornata.', 'success')
        return redirect(url_for('ai_chatbot.admin_plugins'))
    return render_template('ai_chatbot_admin_plugins.html', config=plugin_config(), engines=ENGINE_NAMES, engine_labels=ENGINE_LABELS)


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
            try:
                original = validate_upload_file(upload, allowed_extensions={'.txt', '.md', '.csv', '.json', '.xml', '.html', '.htm', '.log', '.pdf', '.docx'})
            except ValueError as exc:
                flash(str(exc), 'danger')
                return redirect(url_for('ai_chatbot.admin_documents'))
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
