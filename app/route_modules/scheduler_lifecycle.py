"""Background scheduler lifecycle helpers for route modules and tests.

The application keeps scheduler entry points in ``app.routes`` for backwards
compatibility, while this module centralizes environment/test detection and
thread shutdown primitives.  Keeping this logic outside the large route module
reduces coupling and makes pytest shutdown behaviour easier to validate.
"""
from __future__ import annotations

import os
import sys
from threading import Event, Thread
from typing import Iterable

_TRUE_VALUES = {'1', 'true', 'yes', 'on'}


def truthy_env(name: str) -> bool:
    """Return True when an environment variable is explicitly enabled."""
    return os.getenv(name, '').strip().lower() in _TRUE_VALUES


def background_schedulers_disabled(app=None) -> bool:
    """Return True when in-process background schedulers must not start.

    Test runs create many short-lived Flask app instances.  Scheduler threads in
    those processes can keep references to old app contexts and temporary SQLite
    databases, which in turn can make a complete pytest run hang after all tests
    have reported their outcome.  Production remains enabled by default.
    """
    if truthy_env('CIR_DISABLE_BACKGROUND_SCHEDULERS'):
        return True
    if truthy_env('CIR_ENABLE_SCHEDULERS_DURING_TESTS'):
        return False
    if app is not None and app.config.get('TESTING'):
        return True
    return bool(os.getenv('PYTEST_CURRENT_TEST') or 'pytest' in sys.modules)


def stop_threads(stop_events: Iterable[Event], threads: Iterable[Thread | None], timeout: float = 2.0) -> list[str]:
    """Signal scheduler threads to stop and return names still alive after join."""
    alive: list[str] = []
    for event in stop_events:
        try:
            event.set()
        except Exception as exc:
            alive.append(f"event-stop-error:{type(exc).__name__}")
    for thread in threads:
        if not thread:
            continue
        try:
            if thread.is_alive():
                thread.join(timeout=timeout)
            if thread.is_alive():
                alive.append(thread.name)
        except Exception:
            alive.append(getattr(thread, 'name', repr(thread)))
    return alive
