#!/usr/bin/env python3
"""External worker used by Round 15 crash/restart integration tests.

The parent process kills this worker with SIGKILL after it has activated the
new persistent snapshot.  No Python exception/finally handler can therefore
participate in recovery.
"""
import argparse
import json
import os
from pathlib import Path
import time

from flask import Flask

from app import db, routes


def build_app(database_url: str, root: Path) -> Flask:
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI=database_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        UPLOAD_DIR=str(root / 'uploads'),
        FORM_TEMPLATE_DIR=str(root / 'form_templates'),
        LOGO_DIR=str(root / 'logo'),
        SSO_LOGO_DIR=str(root / 'sso'),
        SSL_DIR=str(root / 'ssl'),
        AI_CHATBOT_DOC_DIR=str(root / 'ai_docs'),
        BACKUP_DIR=str(root / 'backups'),
    )
    db.init_app(app)
    return app


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--database-url', required=True)
    parser.add_argument('--root', required=True)
    parser.add_argument('--mode', choices=('precommit', 'postcommit'), required=True)
    parser.add_argument('--ready-file', required=True)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    ready = Path(args.ready_file).resolve()
    app = build_app(args.database_url, root)

    with app.app_context():
        db.create_all()
        base = Path(app.config['UPLOAD_DIR'])
        txn = routes._FullImportFilesystemTransaction(None, {})
        # Limit this purpose-built crash harness to one managed volume while
        # exercising the exact production transaction/journal implementation.
        txn.paths = {'uploads': base}
        stage = txn._stage_path('uploads', base)
        (stage / 'new.txt').write_text('new', encoding='utf-8')
        txn.journal = {
            'version': routes._FULL_IMPORT_JOURNAL_VERSION,
            'token': txn.token,
            'created_at': '2026-09-02T00:00:00+00:00',
            'groups': {
                'uploads': {
                    'had_original': base.exists(),
                    'state': 'staged',
                }
            },
        }
        txn._persist_journal()
        txn.activate()
        txn.mark_database_commit_pending()
        if args.mode == 'postcommit':
            db.session.commit()
        else:
            # Ensure the marker reached the database connection while keeping
            # the transaction uncommitted. SIGKILL must make it disappear.
            db.session.flush()

        ready.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({'pid': os.getpid(), 'token': txn.token, 'mode': args.mode})
        with open(ready, 'w', encoding='utf-8') as out:
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
        routes._fsync_directory(ready.parent)

        # The parent deliberately uses SIGKILL, so this loop never exits via
        # application cleanup and cannot run transaction rollback/finalizers.
        while True:
            time.sleep(60)


if __name__ == '__main__':
    raise SystemExit(main())
