import os, sys, time
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

REAL_SLEEP = time.sleep


@pytest.fixture
def fast_coach(tmp_path, monkeypatch):
    """coach module with tiny stage times, short sleeps and settings in a temp folder."""
    import coach as K
    monkeypatch.setattr(K, 'STAGE_TIME', [0.001] * 4)
    monkeypatch.setattr(K.time, 'sleep', lambda s: REAL_SLEEP(min(s, 0.004)))
    monkeypatch.setattr(K, 'SETTINGS', str(tmp_path / 'coach_settings.json'))
    monkeypatch.setattr(K, 'PROGRESS', str(tmp_path / 'coach_progress.json'))
    monkeypatch.setattr(K, 'LOGF', str(tmp_path / 'coach.log'))
    return K


def wait_for(cond, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        REAL_SLEEP(0.02)
    return False
