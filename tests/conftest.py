"""Pytest lifecycle helpers for the Flask application test suite."""
import sys


def pytest_sessionfinish(session, exitstatus):
    """Ensure background scheduler threads cannot survive a full test run."""
    try:
        from app.routes import stop_background_schedulers
        stop_background_schedulers(timeout=0.5)
    except Exception:
        pass
    sys.stdout.flush()
    sys.stderr.flush()
