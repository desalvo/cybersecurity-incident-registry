"""Run automatic database upgrades before the container starts web workers.

The same upgrade is also part of create_app(), so non-container starts retain
the same protection. Failure exits nonzero; this command never skips a schema
check, imports an archive, resets existing passwords or enables schedulers.
"""
import os


def main():
    os.environ['CIR_DISABLE_BACKGROUND_SCHEDULERS'] = '1'
    from . import create_app, db
    from .migration_manager import SCHEMA_REVISIONS, assert_schema_supported

    app = create_app()
    with app.app_context():
        plan = assert_schema_supported(db.engine)
        if plan.pending_ids:
            raise RuntimeError('Automatic database upgrade did not reach the required schema revision.')
        app.logger.info('Automatic database upgrade ready: schema revision %s', SCHEMA_REVISIONS[-1])
        db.session.remove()
        db.engine.dispose()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
