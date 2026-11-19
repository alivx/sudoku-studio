"""Sudoku Studio controller: Learn with manual Next, Play with a stand-in bot, one task at a time."""
import json, time, types
import pytest

from conftest import wait_for, REAL_SLEEP


class FakeUI:
    def __init__(self): self.states, self.ovs, self.overlay_on, self.stopped = [], [], False, False
    def app_state(self, st): self.states.append(json.loads(json.dumps(st, default=str)))
    def overlay(self, d): self.ovs.append(d)
    def show_overlay(self, on): self.overlay_on = on
    def lang_changed(self, lang): pass
    def phone_window(self): return None
    def stop(self): self.stopped = True


@pytest.fixture
def studio(fast_coach, tmp_path, monkeypatch):
    import sudoku_app as A
    import sudoku_auto as SA
    monkeypatch.setattr(A, 'APP_SETTINGS', str(tmp_path / 'app_settings.json'))
    monkeypatch.setattr(SA, 'LOGF', str(tmp_path / 'sudoku_auto.log'))
    monkeypatch.setattr(SA, 'log', SA.log)          # the app wraps SA.log; restore it afterwards
    monkeypatch.setattr(fast_coach, 'check_permissions', lambda: None)
    apps = []

    def make(demo):
        app = A.App(types.SimpleNamespace(lang='en', demo=demo))
        app.ui = FakeUI()
        apps.append(app)
        return app, app.ui

    yield make, SA
    for app in apps:
        app.cmdq.put({'cmd': 'quit'})
        wait_for(lambda: app.ui.stopped, 3)
        for t in (app.bot_thread, app.coach_thread):
            if t:
                t.join(3)


def fake_bot(SA, slow=False):
    class FakeBot:
        def __init__(self, args):
            self.a, self.done, self.t0, self.n = args, 0, time.time(), 0
            self.ph = types.SimpleNamespace(ensure_front=lambda: None)

        def step(self):
            self.n += 1
            REAL_SLEEP(0.05 if slow else 0.01)
            if slow:
                return False
            if self.n % 10 == 1:
                SA.log('new puzzle: 58 empty cells')
                self.t0 = time.time()
            elif self.n % 10 == 9:
                self.done += 1
                SA.log(f'*** game {self.done}/{self.a.games} complete in {40 + self.done}s')
                return self.done >= self.a.games
            else:
                SA.log(f'entered 6 cell(s) by number, {58 - 6 * (self.n % 10)} left')
            return False
    return FakeBot


def test_learn_waits_for_next(studio):
    make, SA = studio
    app, ui = make(demo=True)
    app.cmdq.put({'cmd': 'view', 'value': 'learn'})
    app.cmdq.put({'cmd': 'learn_start'})
    last = lambda: ui.states[-1]['learn'] if ui.states else {}
    assert wait_for(lambda: ui.states and ui.states[-1]['learning'] and last().get('view') == 'lesson', 5)
    assert not last().get('playing'), 'Learn must not start on autopilot'
    step = last().get('stepNo')
    REAL_SLEEP(0.6)
    assert last().get('stepNo') == step
    for _ in range(4):
        app.cmdq.put({'cmd': 'next'})
        REAL_SLEEP(0.2)
    assert wait_for(lambda: last().get('stepNo', 0) > step, 4)
    assert ui.overlay_on
    app.cmdq.put({'cmd': 'lang'})
    assert wait_for(lambda: ui.states[-1]['lang'] == 'ar' and last().get('lang') == 'ar')
    app.cmdq.put({'cmd': 'learn_stop'})
    assert wait_for(lambda: not ui.states[-1]['learning'])
    assert not ui.overlay_on


def test_play_runs_pauses_and_stops(studio, monkeypatch):
    make, SA = studio
    monkeypatch.setattr(SA, 'Bot', fake_bot(SA))
    app, ui = make(demo=False)
    run = lambda: ui.states[-1]['play']['run']
    app.cmdq.put({'cmd': 'play_set', 'key': 'games', 'value': 3})
    app.cmdq.put({'cmd': 'play_start'})
    assert wait_for(lambda: ui.states and run()['state'] == 'done', 10)
    assert run()['done'] == 3 and len(run()['results']) == 3

    app.cmdq.put({'cmd': 'play_set', 'key': 'games', 'value': 2})
    app.cmdq.put({'cmd': 'play_start'})
    REAL_SLEEP(0.05)
    app.cmdq.put({'cmd': 'play_pause'})
    assert wait_for(lambda: run()['state'] == 'paused')
    done = run().get('done')
    REAL_SLEEP(0.3)
    assert run()['state'] == 'paused' and run().get('done') == done
    app.cmdq.put({'cmd': 'play_stop'})
    assert wait_for(lambda: run()['state'] == 'stopped', 5)


def test_only_one_task_uses_the_phone(studio, monkeypatch):
    make, SA = studio
    monkeypatch.setattr(SA, 'Bot', fake_bot(SA, slow=True))
    app, ui = make(demo=False)
    run = lambda: ui.states[-1]['play']['run']
    app.cmdq.put({'cmd': 'play_start'})
    assert wait_for(lambda: ui.states and run()['state'] == 'running')
    app.a.demo = True
    app.cmdq.put({'cmd': 'learn_start'})
    assert wait_for(lambda: ui.states[-1]['learning'] and run()['state'] == 'stopped', 10)
    assert ui.states[-1]['learnNotice']
    app.a.demo = False
    app.cmdq.put({'cmd': 'play_start'})
    assert wait_for(lambda: not ui.states[-1]['learning'] and run()['state'] == 'running', 10)
    assert ui.states[-1]['play']['notice']
