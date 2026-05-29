import threading


def test_create_app_does_not_start_background_schedulers_during_pytest(monkeypatch, tmp_path):
    from tests.test_ui_regressions_0_5_0_1 import _configure_test_env

    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app

    app = create_app()
    app.config['TESTING'] = True

    names = {t.name for t in threading.enumerate()}
    assert 'cir-deadline-notification-scheduler' not in names
    assert 'cir-incident-reminder-scheduler' not in names
    assert 'cir-backup-scheduler' not in names


def test_background_scheduler_stop_api_is_safe_when_not_started():
    from app.routes import stop_background_schedulers

    stop_background_schedulers(timeout=0.1)
