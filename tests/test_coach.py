"""The coach on the practice puzzle (no phone): manual Next, your turn, review, errors."""
import threading, types
import pytest

from conftest import wait_for, REAL_SLEEP


class NullUI:
    def __init__(self): self.panels, self.ovs, self.closed = [], [], False
    def panel(self, st): self.panels.append(st)
    def overlay(self, d): self.ovs.append(d)
    def lang_changed(self, lang): pass
    def close(self): self.closed = True


def start(K, placer, auto=True, lang='en'):
    with open(K.SETTINGS, 'w') as f:
        f.write('{"auto": %s}' % ('true' if auto else 'false'))
    ph = K.DemoPhone()
    SA = K.demo_sa(ph)
    ui = NullUI()
    args = types.SimpleNamespace(lang=lang, placer=placer, speed='fast', eastern=False, level='extreme',
                                 delay=0, demo=True)
    c = K.Coach(args, ui, ph, SA)
    t = threading.Thread(target=c.run, daemon=True)
    t.start()
    return c, t, ph, SA, ui


def stop(c, t):
    c.command({'cmd': 'quit'})
    t.join(3)


def solved(ui):
    return any(p.get('view') == 'summary' for p in ui.panels[-3:])


def test_coach_solves_practice_puzzle(fast_coach):
    c, t, ph, SA, ui = start(fast_coach, 'coach')
    try:
        assert wait_for(lambda: solved(ui), 30)
        assert all(ph.board)
        assert all('step' in o for o in ui.ovs)
    finally:
        stop(c, t)


def test_manual_next_waits(fast_coach):
    c, t, ph, SA, ui = start(fast_coach, 'coach', auto=False)
    try:
        assert wait_for(lambda: ui.panels and ui.panels[-1].get('view') == 'lesson', 5)
        stage = ui.panels[-1].get('stage')
        REAL_SLEEP(0.5)
        assert ui.panels[-1].get('stage') == stage, 'moved on without Next'
        c.command({'cmd': 'next'})
        assert wait_for(lambda: ui.panels[-1].get('stage') != stage, 3)
    finally:
        stop(c, t)


def test_me_mode_catches_wrong_number(fast_coach):
    state = {'wrong': False}
    c, t, ph, SA, ui = start(fast_coach, 'me', lang='ar')

    def player():
        last = ui.panels[-1] if ui.panels else {}
        if last.get('yourTurn') and last.get('step') and last['step'].get('place'):
            i, d = last['step']['place']
            if not state['wrong']:
                ph.board[i] = d % 9 + 1
                state['wrong'] = True
            elif ph.board[i] != d:
                ph.board[i] = d
        return solved(ui)

    try:
        assert wait_for(player, 40)
        keys = {(p.get('status') or {}).get('key') for p in ui.panels}
        assert 'not_that' in keys and 'correct' in keys
        assert any(p.get('step') and p['step']['tech'] == 'mistake' for p in ui.panels)
    finally:
        stop(c, t)


def test_review_earlier_steps(fast_coach):
    c, t, ph, SA, ui = start(fast_coach, 'coach')
    try:
        assert wait_for(lambda: len(c.history) >= 5, 10)
        for m in ('play', 'back', 'back', 'next', 'next', 'next', 'play'):
            c.command({'cmd': m})
            REAL_SLEEP(0.05)
        assert wait_for(lambda: solved(ui), 30)
        assert any(p.get('review') for p in ui.panels)
    finally:
        stop(c, t)


def test_missing_window_shows_error_and_retry(fast_coach):
    K = fast_coach
    with open(K.SETTINGS, 'w') as f:
        f.write('{"auto": true}')
    ph = K.DemoPhone()
    SA = K.demo_sa(ph)
    ui = NullUI()
    mode = {'screen': 'other', 'fail': False}
    real_classify, real_shot = SA.classify, ph.stable_shot
    SA.classify = lambda a: ('other', None) if mode['screen'] == 'other' else real_classify(a)

    def shot(tries=3):
        if mode['fail']:
            mode['fail'] = False
            raise SA.Stop('"iPhone Mirroring" window not found - open iPhone Mirroring and unlock the phone.')
        return real_shot()

    ph.stable_shot = shot
    args = types.SimpleNamespace(lang='en', placer='coach', speed='fast', eastern=False, level='extreme',
                                 delay=0, demo=True)
    c = K.Coach(args, ui, ph, SA)
    t = threading.Thread(target=c.run, daemon=True)
    t.start()
    try:
        assert wait_for(lambda: ui.panels and ui.panels[-1]['view'] == 'empty', 5)
        mode['fail'] = True
        assert wait_for(lambda: ui.panels[-1]['view'] == 'error', 5)
        assert ui.panels[-1]['error']['kind'] == 'no_window'
        mode['screen'] = 'game'
        c.command({'cmd': 'retry'})
        assert wait_for(lambda: ui.panels[-1]['view'] in ('lesson', 'summary'), 5)
    finally:
        stop(c, t)
    assert ui.closed


@pytest.mark.parametrize('msg,kind', [
    ('"iPhone Mirroring" window not found', 'no_window'),
    ('Screen Recording permission is off', 'permission'),
    ('unknown pop-up with one button', 'popup'),
    ('the screen did not change after the tap', 'stuck'),
    ('something else', 'other'),
])
def test_error_kind(fast_coach, msg, kind):
    assert fast_coach.error_kind(msg) == kind
