"""Pytest lifecycle helpers for the Flask application test suite."""
import os
import sys
from pathlib import Path


def pytest_cmdline_main(config):
    """Optionally run the complete suite through isolated module processes.

    Module isolation is intentionally opt-in through
    ``CIR_PYTEST_SUITE_ISOLATION=1``. Normal ``pytest`` invocations retain
    standard pytest semantics, while CI/offline jobs can explicitly select the
    deterministic isolated runner.
    """
    if os.environ.get('CIR_PYTEST_ISOLATED_CHILD') == '1':
        return None
    if os.environ.get('CIR_PYTEST_SUITE_ISOLATION', '').lower() not in {'1', 'true', 'yes'}:
        return None
    args = [str(arg) for arg in getattr(config, 'args', []) or []]
    normalized = {arg.rstrip('/').replace('\\', '/') for arg in args}
    whole_suite = not args or normalized in ({'tests'}, {'./tests'})
    if not whole_suite:
        return None
    root = Path(__file__).resolve().parents[1]
    runner = root / 'scripts' / 'run_pytest_offline_safe.sh'
    if not runner.exists():
        return None
    env = os.environ.copy()
    env.setdefault('PYTEST_DISABLE_PLUGIN_AUTOLOAD', '1')
    env.setdefault('CIR_DISABLE_BACKGROUND_SCHEDULERS', '1')
    env.setdefault('CIR_FORCE_PYTEST_PROCESS_EXIT', '1')
    env['CIR_PYTEST_ISOLATED_CHILD'] = '1'
    os.execvpe('bash', ['bash', str(runner)], env)
    return 2


def pytest_configure(config):
    """Make direct pytest invocations deterministic in Docker/offline runners."""
    os.environ.setdefault('PYTEST_VERSION', 'agid')
    os.environ.setdefault('CIR_TEST_PASSWORD_HASH_METHOD', 'pbkdf2:sha256:1')
    os.environ.setdefault('PYTEST_DISABLE_PLUGIN_AUTOLOAD', '1')
    os.environ.setdefault('CIR_DISABLE_BACKGROUND_SCHEDULERS', '1')


def pytest_runtest_teardown(item, nextitem):
    """Release Flask-SQLAlchemy state between tests in full-suite runs.

    Many tests create independent Flask apps against different temporary SQLite
    databases.  Disposing per-app engines prevents leaked pooled connections or
    old app contexts from slowing/blocking later tests when the whole suite is
    executed in a single pytest process.
    """
    try:
        from app import db
        db.session.remove()
        app_engines = getattr(db, '_app_engines', None)
        if app_engines:
            for engines in list(app_engines.values()):
                for engine in list(engines.values()):
                    try:
                        engine.dispose()
                    except Exception:
                        pass
    except Exception:
        pass


def pytest_sessionfinish(session, exitstatus):
    """Ensure background scheduler threads cannot survive a full test run."""
    try:
        from app.routes import stop_background_schedulers
        stop_background_schedulers(timeout=0.5)
    except Exception:
        pass
    try:
        from app import db
        db.session.remove()
    except Exception:
        pass
    try:
        import threading
        alive = [f"{t.name}:daemon={t.daemon}" for t in threading.enumerate() if t is not threading.current_thread()]
        if alive:
            print("PYTEST_ALIVE_THREADS=" + ";".join(alive), flush=True)
    except Exception:
        pass
    sys.stdout.flush()
    sys.stderr.flush()
    if os.environ.get('CIR_FORCE_PYTEST_PROCESS_EXIT', '').lower() in {'1', 'true', 'yes'}:
        # Docker/offline compliance runners and full-suite local invocations may
        # otherwise hang after pytest has reported success because optional PDF,
        # image or network libraries leave non-essential atexit handlers/resources
        # alive.  Tests in this project do not rely on post-session interpreter
        # state, so isolated Docker runners may opt into deterministic process shutdown.
        # The isolated runner enables this so each child process exits
        # deterministically after pytest reports the module result.
        os._exit(int(exitstatus or 0))
