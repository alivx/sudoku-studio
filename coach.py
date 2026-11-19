#!/usr/bin/env python3
"""coach.py - Sudoku training coach, mode 1: Watch and learn (English / Arabic). Rule-based, no AI.

The coach reads the board from iPhone Mirroring, finds the easiest logical step (logic.py),
explains it in four stages - Where, What, Why, Answer - with animations drawn on a
click-through layer over the phone, then places the number (or waits for you to).

Run (from the project folder, same permissions as sudoku_auto.py):
    .venv/bin/python coach.py                  # English
    .venv/bin/python coach.py --lang ar        # Arabic
    .venv/bin/python coach.py --placer me      # you place every number yourself
    .venv/bin/python coach.py --demo           # try the screens without the phone
Keys (click the panel first): Space play/pause, -> next, <- back, L language.
"""
import sys, os, time, json, threading, argparse, queue, types, traceback, subprocess
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import logic as L

WEB = os.path.join(HERE, 'web')
SETTINGS = os.path.join(HERE, 'coach_settings.json')
PROGRESS = os.path.join(HERE, 'coach_progress.json')
LOGF = os.path.join(HERE, 'coach.log')
STAGE_TIME = [1.4, 2.0, 3.6, 1.6]                       # where, what, why, answer (seconds at normal speed)
SPEED = {'slow': 1.7, 'normal': 1.0, 'fast': 0.45}
QUICK = {'full_house': .6, 'mistake': .8}               # trivial steps go faster


def log(m):
    line = time.strftime('%H:%M:%S ') + m
    print(line, flush=True)
    try:
        with open(LOGF, 'a') as f:
            f.write(line + '\n')
    except OSError:
        pass


def load_json(path, default):
    try:
        with open(path) as f:
            return {**default, **json.load(f)}
    except (OSError, ValueError):
        return dict(default)


def save_json(path, data):
    try:
        with open(path, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except OSError:
        pass


def error_kind(msg):
    """Map a technical stop message to a plain-language reason (keys in i18n 'errors')."""
    low = str(msg).lower()
    if 'not found' in low or 'to the front' in low:
        return 'no_window'
    if 'permission' in low or 'screen recording' in low or 'accessibility' in low or 'screenshot failed' in low:
        return 'permission'
    if 'pop-up' in low or 'popup' in low:
        return 'popup'
    if 'did not change' in low or 'no progress' in low or 'would not take' in low:
        return 'stuck'
    return 'other'


def check_permissions():
    """Fail early, in plain words, if macOS blocks clicks or screenshots."""
    import sudoku_auto as SA
    try:
        import HIServices
        if not HIServices.AXIsProcessTrusted():
            raise SA.Stop('Accessibility permission is off: clicks are blocked.')
    except ImportError:
        pass
    try:
        import Quartz
        if not Quartz.CGPreflightScreenCaptureAccess():
            raise SA.Stop('Screen Recording permission is off: screenshots are blocked.')
    except (ImportError, AttributeError):
        pass


class Quit(Exception):
    pass


class Coach:
    """Runs on a worker thread. Talks to the screens through `ui` and to the phone through `ph`."""

    KEEP = ('next', 'back', 'next_puzzle', 'stage', 'reveal', 'live', 'retry')

    def __init__(self, args, ui, ph, sa):
        self.a, self.ui, self.ph, self.SA = args, ui, ph, sa
        st = load_json(SETTINGS, {'lang': 'en', 'speed': 'normal', 'placer': 'coach', 'showCands': False,
                                  'eastern': False, 'quickBasics': True, 'auto': False})
        for k in ('lang', 'speed', 'placer'):
            if getattr(args, k, None):
                st[k] = getattr(args, k)
        if getattr(args, 'eastern', False):
            st['eastern'] = True
        self.state = {'lang': st['lang'], 'speed': st['speed'], 'placer': st['placer'], 'showCands': st['showCands'],
                      'eastern': st['eastern'], 'quickBasics': st['quickBasics'], 'playing': bool(st['auto']),
                      'view': 'loading', 'step': None, 'stage': 0, 'review': None, 'yourTurn': False,
                      'used': {}, 'seen': {}, 'status': None, 'progress': None, 'stepNo': 0}
        self.cmds = queue.Queue()
        self.progress = load_json(PROGRESS, {'games': 0, 'watched': {}})
        self.nav = False
        self.nav_taps = {}
        self.overlay_last = {'step': None}
        self.new_puzzle()
        self.watch_mouse()

    # ------------------------------------------------------------ plumbing
    def command(self, msg):            # called from the UI thread
        self.cmds.put(msg)

    def push(self, overlay=None):
        self.state['seen'] = {k: self.progress['watched'].get(k, 0) + self.used.get(k, 0)
                              for k in set(self.progress['watched']) | set(self.used)}
        if self.sol is not None and getattr(self, 'board', None):
            self.state['progress'] = {'filled': self.total - sum(1 for x in self.board if not x),
                                      'total': self.total, 'elapsed': int(time.time() - self.t0)}
        self.ui.panel(dict(self.state))
        if overlay is not None:
            self.overlay_last = overlay
            self.ui.overlay(overlay)

    def status(self, key=None, tone=None, **p):
        new = {'key': key, 'p': p, 'tone': tone} if key else None
        if new != self.state['status']:
            self.state['status'] = new
            self.push()

    def view(self, name, **extra):
        changed = self.state['view'] != name or any(self.state.get(k) != v for k, v in extra.items())
        self.state['view'] = name
        self.state.update(extra)
        if changed:
            if name != 'lesson':
                self.state['step'] = None
            self.push({'step': None, 'lang': self.state['lang'], 'memory': self.memory()})

    def memory(self):
        """Cells where earlier steps removed options: what is still possible there."""
        if not getattr(self, 'board', None) or not self.elims:
            return []
        cands = L.candidates(self.board, self.elims)
        cells = sorted({i for i, _ in self.elims if not self.board[i]})
        return [[i, sorted(cands[i])] for i in cells]

    def overlay_data(self, step, stage, board=None, cands=None, **extra):
        board = board if board is not None else getattr(self, 'board', None)
        cands = cands if cands is not None else getattr(self, 'cands', None)
        d = {'step': step, 'stage': stage, 'showCands': self.state['showCands'], 'demo': bool(self.a.demo),
             'lang': self.state['lang'], 'eastern': self.state['eastern'], 'memory': self.memory(),
             'board': board, 'cands': [sorted(c) for c in cands] if cands else None}
        d.update(extra)
        return d

    def save_settings(self):
        data = {k: self.state[k] for k in ('lang', 'speed', 'placer', 'showCands', 'eastern', 'quickBasics')}
        data['auto'] = self.state['playing']
        save_json(SETTINGS, data)

    def apply_setting(self, m):
        cmd, v = m.get('cmd'), m.get('value')
        if cmd == 'quit':
            raise Quit()
        if cmd == 'lang':
            self.state['lang'] = ('ar' if self.state['lang'] == 'en' else 'en') if v not in ('en', 'ar') else v
            self.ui.lang_changed(self.state['lang'])
        elif cmd == 'speed' and v in SPEED:
            self.state['speed'] = v
        elif cmd == 'placer' and v in ('coach', 'me'):
            self.state['placer'] = v
        elif cmd in ('cands', 'quick', 'eastern'):
            key = {'cands': 'showCands', 'quick': 'quickBasics', 'eastern': 'eastern'}[cmd]
            self.state[key] = v is True or v == 1 or str(v).lower() == 'true'
        elif cmd == 'play':                                  # Auto-advance on/off (off = you press Next)
            self.state['playing'] = not self.state['playing'] if v is None else (v is True or v == 1 or str(v).lower() == 'true')
        elif cmd == 'open_log':
            subprocess.run(['open', LOGF], capture_output=True)
            return True
        elif cmd in ('ready', 'overlay_ready'):
            pass
        elif cmd == 'js_error':
            log('screen error: ' + str(m.get('msg')))
            return True
        else:
            return False
        if cmd not in ('ready', 'overlay_ready'):
            self.save_settings()
        return True

    def drain(self, keep=KEEP):
        """Apply setting commands now; return the first navigation command as a dict (or None)."""
        while True:
            try:
                m = self.cmds.get_nowait()
            except queue.Empty:
                return None
            if m.get('cmd') in keep:
                return m
            if self.apply_setting(m):
                ov = None
                if self.overlay_last.get('step') is not None or self.overlay_last.get('memory') is not None:
                    ov = dict(self.overlay_last, showCands=self.state['showCands'], lang=self.state['lang'],
                              eastern=self.state['eastern'])
                self.push(ov)

    def sleep(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            m = self.drain()
            if m:
                return m
            time.sleep(0.05)
        return None

    def watch_mouse(self):
        """Tell the panel when the phone tapping pauses because you moved the mouse."""
        orig = getattr(self.ph, 'guard_mouse', None)
        if orig is None:
            return
        def guarded():
            moved = False
            if self.ph.last_tap is not None:
                try:
                    x, y = self.ph._mouse()
                    moved = abs(x - self.ph.last_tap[0]) + abs(y - self.ph.last_tap[1]) > 4
                except Exception:
                    pass
            if moved:
                self.status('mouse_paused', 'warning')
            orig()
        self.ph.guard_mouse = guarded

    # ------------------------------------------------------------ puzzle state
    def new_puzzle(self):
        self.sol = None
        self.givens = None
        self.elims = set()
        self.history = []
        self.used = Counter()
        self.t0 = time.time()
        self.total = 0
        self.active = False
        self.board = None
        self.state.update(used={}, progress=None, stepNo=0)

    def read_board(self, im, stable):
        SA = self.SA
        grid = SA.crop_grid(im)
        g = SA.read(grid)
        busy = getattr(SA, 'board_busy', None)
        if not stable or (busy and busy(SA.arr(im))) or not SA.valid(g):
            return None
        g2 = SA.read(SA.crop_grid(self.ph.shot()))
        if g2 != g:
            return None
        clues = SA.original_clues(grid, g) if hasattr(SA, 'original_clues') else g
        return g, clues

    def identify(self, g, clues):
        SA = self.SA
        board = L.parse(g)
        if self.sol is not None:
            given_now = [i for i, ch in enumerate(''.join(clues)) if ch != '.']
            if sum(1 for i in given_now if board[i] != self.sol[i]) < 2:
                return True
            log('a different puzzle is on screen')
            self.new_puzzle()
        for src in (clues, g):
            n, s = SA.solve(src)
            if n == 1:
                self.sol = L.parse(s)
                self.givens = [ch != '.' for ch in ''.join(src)]
                self.total = sum(1 for x in self.givens if not x)
                self.active = True
                self.t0 = time.time()
                log(f'new puzzle: {sum(1 for x in board if not x)} empty cells')
                return True
        return False

    # ------------------------------------------------------------ the main loop
    def run(self):
        try:
            self.push()
            while True:
                try:
                    while True:
                        self.tick()
                except (self.SA.Stop, Exception) as e:
                    if isinstance(e, Quit):
                        raise
                    self.show_error(e)
                    while True:                                  # wait for Try again / Close
                        m = self.drain(keep=('retry',))
                        if m:
                            log('retry')
                            self.state['error'] = None
                            self.view('loading')
                            break
                        time.sleep(0.1)
        except Quit:
            log('coach stopped by you')
        finally:
            self.ui.close()

    def show_error(self, e):
        msg = str(e)
        if not isinstance(e, self.SA.Stop):
            log('ERROR: ' + traceback.format_exc())
            msg = f'{type(e).__name__}: {e}'
        else:
            log('STOPPED: ' + msg)
        kind = error_kind(msg)
        self.state['status'] = None
        self.view('error', error={'kind': kind, 'msg': msg})

    def tick(self):
        im, stable, prev = self.ph.stable_shot(tries=3)
        state, info = self.SA.classify(self.SA.arr(im))
        if state not in ('game', 'other') and not stable:
            s2, i2 = self.SA.classify(self.SA.arr(prev))
            stable = s2 == state and self.SA.close(info, i2)
        if state != getattr(self, 'last_state', None):
            log(f'sees: {state}')
            self.last_state = state
            self.nav_taps = {}
        if state == 'game':
            self.nav = False
            return self.game_tick(im, stable)
        if state == 'complete' and self.active:
            self.finish_game()
        if self.nav and stable and state in ('complete', 'sheet', 'home', 'popup'):
            return self.navigate(state, info)
        if self.state['view'] != 'summary':
            self.view('empty', empty='finished' if state == 'complete' else 'no_game')
        if not self.nav:
            self.status('waiting' if state != 'complete' else None)
        m = self.sleep(0.8)
        if m and m['cmd'] in ('next', 'next_puzzle') and state in ('complete', 'home'):
            self.nav = True

    def navigate(self, state, info):
        self.status('new_game')
        if self.a.demo:
            self.ph.board = L.parse(DemoPhone.PUZZLE)
            return self.sleep(0.5)
        n = self.nav_taps.get(state, 0) + 1
        self.nav_taps[state] = n
        if n > 6:
            raise self.SA.Stop(f'tapped {state} {n - 1} times but the screen did not change')
        if state in ('complete', 'home'):
            y = info
        elif state == 'sheet':
            y = info[self.a.level]
        else:
            kind, py, sy = info
            if kind != 'two':
                self.status('check_phone', 'warning')
                return self.sleep(1)
            y = sy
        self.ph.ensure_front()
        self.ph.last_tap = None
        self.ph.tap(170, y, pause=1.2)

    def finish_game(self):
        secs = int(time.time() - self.t0)
        hardest = max(self.used, key=lambda k: (L.TIER[k] if k != 'mistake' else 0, self.used[k]), default=None)
        self.progress['games'] += 1
        for k, v in self.used.items():
            self.progress['watched'][k] = self.progress['watched'].get(k, 0) + v
        save_json(PROGRESS, self.progress)
        log(f'puzzle solved in {secs}s, steps: {dict(self.used)}')
        summary = {'time': secs, 'steps': sum(self.used.values()), 'hardest': hardest, 'used': dict(self.used)}
        self.new_puzzle()
        self.state['status'] = None
        self.view('summary', summary=summary)

    def game_tick(self, im, stable):
        read = self.read_board(im, stable)
        if not read:
            if self.state['view'] not in ('lesson', 'loading'):
                self.view('loading')
            self.status('reading')
            return self.sleep(0.5)
        g, clues = read
        if not self.identify(g, clues):
            self.view('loading')
            self.status('reading')
            return self.sleep(0.6)
        board = L.parse(g)
        self.board = board
        if board == self.sol:
            self.status('solved_wait')
            return self.sleep(0.6)
        cands = L.candidates(board, self.elims)
        if any(not board[i] and not cands[i] for i in range(81)):
            self.elims = set()
            cands = L.candidates(board, self.elims)
        step = L.next_step(board, cands, self.sol, self.givens)
        if step is None:
            return self.sleep(0.6)
        self.cands = cands
        self.state['stepNo'] = len(self.history) + 1
        self.state['view'] = 'lesson'
        if (self.state['status'] or {}).get('key') in ('reading', 'waiting', 'new_game', 'correct', 'mouse_paused', 'placing'):
            self.state['status'] = None
        self.present(step)
        self.act(step, board)

    # ------------------------------------------------------------ teaching
    def known(self, tech):
        return self.progress['watched'].get(tech, 0) + self.used.get(tech, 0)

    def present(self, step):
        """Play the stages. 'Me' mode stops before the answer and waits for you."""
        me = (self.state['placer'] == 'me' and step['place'] is not None and step['tech'] != 'reveal')
        quick = (self.state['quickBasics'] and not me and step['tier'] <= 1 and self.known(step['tech']) >= 5)
        stages = [0, 3] if quick else [0, 1, 2, 3]
        mult = 0.55 if quick else QUICK.get(step['tech'], 1)
        self.me_step = me
        self.state.update(step=step, review=None, yourTurn=me, view='lesson')
        k = 0
        while k < len(stages):
            stage = stages[k]
            if me and stage == 3:
                return                                    # you place it; act() waits and offers "Show answer"
            self.state['stage'] = stage
            self.push(self.overlay_data(step, stage))
            wait = STAGE_TIME[stage] * SPEED[self.state['speed']] * mult
            m = self.sleep(wait) if self.state['playing'] else self.wait_cmd()
            cmd = m and m['cmd']
            if cmd == 'back':
                self.review()
                continue
            if cmd == 'stage':
                target = int(m.get('value', 0))
                if me and target == 3:
                    return self.reveal_now(step)
                self.pause()
                stages = [0, 1, 2, 3]
                k = target
                continue
            if cmd == 'reveal' and me:
                return self.reveal_now(step)
            k += 1

    def reveal_now(self, step):
        self.state['yourTurn'] = False
        self.state['stage'] = 3
        i, d = step['place']
        self.status('your_turn_shown', 'info', d=d, cell=L.cref(i))
        self.push(self.overlay_data(step, 3))

    def pause(self):
        self.state['playing'] = False                         # you took over: wait for Next

    def wait_cmd(self):
        while True:
            m = self.drain()
            if m:
                return m
            if self.state['playing']:
                return None
            time.sleep(0.05)

    def review(self):
        """Previous step / Continue walk through earlier steps; 'Back to current step' returns."""
        if not self.history:
            return
        idx = len(self.history) - 1
        live = self.state['step'], self.state['stage'], self.state['yourTurn']
        while idx < len(self.history):
            past, board, cands = self.history[idx]
            self.state.update(step=past, stage=3, review={'n': idx + 1, 't': len(self.history)}, yourTurn=False)
            self.push(self.overlay_data(past, 3, board, cands))
            m = None
            while not m or m['cmd'] not in ('next', 'back', 'live'):
                m = self.drain()
                time.sleep(0.05)
            if m['cmd'] == 'live':
                break
            idx = max(0, idx - 1) if m['cmd'] == 'back' else idx + 1
        self.state.update(step=live[0], stage=live[1], review=None, yourTurn=live[2])
        self.push(self.overlay_data(live[0], live[1]))

    def act(self, step, board):
        if step['place']:
            i, d = step['place']
            cell = L.cref(i)
            if getattr(self, 'me_step', False):
                self.wait_for_user(step, i, d, board)
            else:
                self.status('placing', 'warning', d=d, cell=cell)
                if self.place(i, d):
                    self.status(None)
        for i, d in step['elim']:
            self.elims.add((i, d))
        self.history.append((step, self.board, self.cands))
        self.used[step['tech']] += 1
        self.state['used'] = dict(self.used)
        self.state['yourTurn'] = False
        log(f"step: {step['tech']}" + (f" -> R{step['place'][0] // 9 + 1}C{step['place'][0] % 9 + 1}={step['place'][1]}"
                                       if step['place'] else f" removes {len(step['elim'])}"))

    def place(self, i, d):
        SA = self.SA
        for attempt in range(3):
            self.ph.ensure_front()
            self.ph.last_tap = None
            self.ph.tap(SA.XS[i % 9], SA.YS[i // 9], pause=self.a.delay)
            self.ph.tap(SA.padx(d), SA.PAD_Y, pause=self.a.delay)
            for _ in range(4):
                time.sleep(0.35)
                g = SA.read(SA.crop_grid(self.ph.shot()))
                if g[i // 9][i % 9] == str(d):
                    return True
            log(f'tap for R{i // 9 + 1}C{i % 9 + 1} did not land (try {attempt + 1})')
        return False

    def wait_for_user(self, step, i, d, board):
        """Your turn: wait until you put a number in the cell. 'Show answer' reveals it meanwhile."""
        SA = self.SA
        while True:
            m = self.drain(keep=('reveal', 'stage', 'next'))
            if m and m['cmd'] == 'next' and self.a.demo and self.state['stage'] == 3:
                self.place(i, d)                          # demo: the practice board can't be tapped, so Next places it
            elif m and (m['cmd'] in ('reveal', 'next') or (m['cmd'] == 'stage' and int(m.get('value', 0)) == 3)):
                self.reveal_now(step)
            elif m and m['cmd'] == 'stage':
                self.state['stage'] = int(m.get('value', 0))
                self.push(self.overlay_data(step, self.state['stage']))
            time.sleep(0.5)
            im = self.ph.shot()
            if SA.classify(SA.arr(im))[0] != 'game':
                return
            g = SA.read(SA.crop_grid(im))
            if not SA.valid(g):
                if sum(r.count('.') for r in g) > 64:
                    continue
                return
            now = L.parse(g)
            if now[i] == d:
                self.board = now
                self.status('correct', 'success', d=d, cell=L.cref(i))
                self.push(self.overlay_data(None, 0, now, None, correct=i))
                time.sleep(1.2)
                return
            if now[i] == board[i]:
                continue
            if now[i]:
                self.status('not_that', 'warning', d=d, cell=L.cref(i))
                time.sleep(1.5)
                return
            if now != board:
                return


# ================================================================ screens (macOS)
class MacUI:
    def __init__(self, on_command, demo=False):
        import objc
        from AppKit import (NSApplication, NSWindow, NSPanel, NSColor, NSScreen, NSMakeRect,
                            NSBackingStoreBuffered, NSApplicationActivationPolicyAccessory)
        from Foundation import NSObject, NSURL, NSTimer
        from WebKit import WKWebView, WKWebViewConfiguration, WKUserContentController
        from PyObjCTools import AppHelper
        self.AppHelper, self.NSMakeRect, self.NSScreen = AppHelper, NSMakeRect, NSScreen
        self.on_command = on_command
        self.demo = demo
        self.pending_overlay, self.pending_panel = None, None
        self.ready = {'panel': False, 'overlay': False}
        self.lang = 'en'
        self.panel_user_moved = False
        self.last_panel_frame = None

        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        ui = self

        class Bridge(NSObject, protocols=[objc.protocolNamed('WKScriptMessageHandler')]):
            def userContentController_didReceiveScriptMessage_(self, ucc, message):
                body = message.body()
                msg = {str(k): (str(v) if isinstance(v, str) else v) for k, v in dict(body).items()}
                if msg.get('cmd') in ('ready', 'overlay_ready'):
                    ui.ready['panel' if msg['cmd'] == 'ready' else 'overlay'] = True
                    log('screen ready: ' + msg['cmd'])
                    ui.flush()
                if msg.get('cmd') == 'cands':
                    v = msg.get('value')
                    msg['value'] = v is True or v == 1 or str(v).lower() == 'true'
                ui.on_command(msg)

        class Ticker(NSObject):
            def tick_(self, _t):
                ui.follow()

        class Closer(NSObject):
            def windowWillClose_(self, _n):
                ui.on_command({'cmd': 'quit'})

        self.bridge, self.ticker, self.closer = Bridge.alloc().init(), Ticker.alloc().init(), Closer.alloc().init()

        def webview(frame, page):
            conf = WKWebViewConfiguration.alloc().init()
            ucc = WKUserContentController.alloc().init()
            ucc.addScriptMessageHandler_name_(self.bridge, 'coach')
            conf.setUserContentController_(ucc)
            wv = WKWebView.alloc().initWithFrame_configuration_(frame, conf)
            wv.setValue_forKey_(False, 'drawsBackground')
            wv.loadFileURL_allowingReadAccessToURL_(NSURL.fileURLWithPath_(os.path.join(WEB, page)),
                                                    NSURL.fileURLWithPath_(WEB))
            return wv

        # click-through animation layer over the phone
        ov = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(NSMakeRect(0, 0, 339, 747), 0, NSBackingStoreBuffered, False)
        ov.setOpaque_(False)
        ov.setBackgroundColor_(NSColor.clearColor())
        ov.setHasShadow_(False)
        ov.setIgnoresMouseEvents_(True)
        ov.setLevel_(3)
        ov.setCollectionBehavior_(1 | 256)
        ov.setReleasedWhenClosed_(False)
        self.ov_web = webview(ov.contentView().bounds(), 'overlay.html')
        self.ov_web.setAutoresizingMask_(18)
        ov.contentView().addSubview_(self.ov_web)
        self.ov = ov

        # coach panel (does not take focus away from iPhone Mirroring)
        style = 1 | 2 | 8 | 128          # titled, closable, resizable, non-activating
        h = min(880, int(NSScreen.mainScreen().visibleFrame().size.height) - 40)
        pn = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(NSMakeRect(0, 0, 372, h), style, NSBackingStoreBuffered, False)
        pn.setTitle_('Sudoku coach')
        pn.setLevel_(3)
        pn.setFloatingPanel_(True)
        pn.setHidesOnDeactivate_(False)
        pn.setBecomesKeyOnlyIfNeeded_(False)
        pn.setCollectionBehavior_(1 | 256)
        pn.setReleasedWhenClosed_(False)
        pn.setDelegate_(self.closer)
        self.pn_web = webview(pn.contentView().bounds(), 'panel.html')
        self.pn_web.setAutoresizingMask_(18)
        pn.contentView().addSubview_(self.pn_web)
        self.pn = pn
        self.follow(force=True)
        pn.orderFrontRegardless()
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(0.3, self.ticker, 'tick:', None, True)

    # -------- window tracking
    def phone_bounds(self):
        from Quartz import CGWindowListCopyWindowInfo, kCGWindowListOptionOnScreenOnly, kCGNullWindowID
        wins = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID) or []
        mine = [w for w in wins if w.get('kCGWindowOwnerName') == 'iPhone Mirroring' and w.get('kCGWindowLayer', 1) == 0]
        if not mine:
            return None
        b = max(mine, key=lambda w: w['kCGWindowBounds']['Height'])['kCGWindowBounds']
        return b['X'], b['Y'], b['Width'], b['Height']

    def follow(self, force=False):
        b = self.phone_bounds()
        main_h = self.NSScreen.screens()[0].frame().size.height
        if b is None and self.demo:
            scr = self.NSScreen.mainScreen().visibleFrame()
            k = min(1.0, (scr.size.height - 80) / 747)
            b = (scr.origin.x + scr.size.width / 2 - 339 * k - 20, 60, 339 * k, 747 * k)
        if b is None:
            if self.ov.isVisible():
                self.ov.orderOut_(None)
            if force:
                self.pn.center()
            return
        X, Y, W, H = b
        frame = self.NSMakeRect(X, main_h - Y - H, W, H)
        if force or getattr(self, 'last_bounds', None) != b:
            self.ov.setFrame_display_(frame, True)
            self.last_bounds = b
            self.place_panel(X, Y, W, H, main_h)
        if not self.ov.isVisible():
            self.ov.orderFrontRegardless()

    def place_panel(self, X, Y, W, H, main_h):
        cur = self.pn.frame()
        if self.last_panel_frame is not None and (abs(cur.origin.x - self.last_panel_frame[0]) > 2
                                                  or abs(cur.origin.y - self.last_panel_frame[1]) > 2):
            self.panel_user_moved = True
        if self.panel_user_moved:
            return
        scr = self.NSScreen.mainScreen().visibleFrame()
        pw, ph = cur.size.width, cur.size.height
        right, left = X + W + 12, X - pw - 12
        fits_r = right + pw <= scr.origin.x + scr.size.width
        fits_l = left >= scr.origin.x
        x = (left if fits_l else right) if self.lang == 'ar' else (right if fits_r else left)
        if not (fits_l or fits_r):
            x = scr.origin.x + scr.size.width - pw
        top = main_h - Y
        y = max(scr.origin.y, min(top - ph, scr.origin.y + scr.size.height - ph))
        self.pn.setFrameOrigin_((x, y))
        self.last_panel_frame = (x, y)

    # -------- thread-safe calls from the coach
    def js(self, wv, code):
        wv.evaluateJavaScript_completionHandler_(code, None)

    def flush(self):
        if self.ready['panel'] and self.pending_panel is not None:
            self.js(self.pn_web, 'panel.update(%s)' % self.pending_panel)
        if self.ready['overlay'] and self.pending_overlay is not None:
            self.js(self.ov_web, 'overlay.render(%s)' % self.pending_overlay)

    def panel(self, state):
        data = json.dumps(state, ensure_ascii=False)
        def go():
            self.pending_panel = data
            if self.ready['panel']:
                self.js(self.pn_web, 'panel.update(%s)' % data)
        self.AppHelper.callAfter(go)

    def overlay(self, data):
        data = json.dumps(data, ensure_ascii=False)
        def go():
            self.pending_overlay = data
            if self.ready['overlay']:
                self.js(self.ov_web, 'overlay.render(%s)' % data)
        self.AppHelper.callAfter(go)

    def lang_changed(self, lang):
        def go():
            self.lang = lang
            b = self.phone_bounds()
            if b:
                self.place_panel(*b, self.NSScreen.screens()[0].frame().size.height)
        self.AppHelper.callAfter(go)

    def close(self):
        self.AppHelper.callAfter(self.AppHelper.stopEventLoop)

    def run(self):
        self.AppHelper.runEventLoop(installInterrupt=True)


# ================================================================ demo phone (no iPhone needed)
class DemoPhone:
    """Pretends to be the phone: a built-in Extreme puzzle that changes when the coach 'taps'."""
    PUZZLE = '.72.3..89' '5..8.....' '8...4....' '...9.287.' '..3..5.2.' '.........' '3...1.5..' '..7......' '......691'

    def __init__(self):
        self.board = L.parse(self.PUZZLE)
        self.sel = None
        self.last_tap = None

    def ensure_front(self): pass
    def stable_shot(self, tries=3): return 'IMG', True, 'IMG'
    def shot(self, *a): return 'IMG'

    def tap(self, fx, fy, pause=None):
        import sudoku_auto as SA
        if fy == SA.PAD_Y and self.sel is not None:
            self.board[self.sel] = 1 + round((fx - 33) / 34)
        elif fy in SA.YS and fx in SA.XS:
            self.sel = SA.YS.index(fy) * 9 + SA.XS.index(fx)
        time.sleep(0.2)


def demo_sa(phone):
    """sudoku_auto look-alike that reads from the demo phone instead of screenshots."""
    import sudoku_auto as real
    ns = types.SimpleNamespace(**{k: getattr(real, k) for k in ('XS', 'YS', 'PAD_Y', 'padx', 'solve', 'valid', 'Stop', 'close')})
    rows = lambda: [''.join(str(x) if x else '.' for x in phone.board[r * 9:r * 9 + 9]) for r in range(9)]
    ns.crop_grid = lambda im: im
    ns.arr = lambda im: im
    ns.read = lambda grid: rows()
    ns.original_clues = lambda grid, g: [''.join(DemoPhone.PUZZLE[r * 9:r * 9 + 9]) for r in range(9)]
    ns.classify = lambda a: ('game', None) if not all(phone.board) else ('complete', 630)
    return ns


def main():
    ap = argparse.ArgumentParser(description='Sudoku training coach - Watch and learn (English/Arabic).')
    ap.add_argument('--lang', choices=['en', 'ar'])
    ap.add_argument('--placer', choices=['coach', 'me'], help='who places the numbers')
    ap.add_argument('--speed', choices=list(SPEED))
    ap.add_argument('--eastern', action='store_true', help='Arabic-Indic numerals in Arabic text')
    ap.add_argument('--level', default='extreme', choices=['easy', 'medium', 'hard', 'expert', 'master', 'extreme'])
    ap.add_argument('--delay', type=float, default=0.15, help='seconds after each tap')
    ap.add_argument('--demo', action='store_true', help='practice puzzle on screen, no phone needed')
    args = ap.parse_args()

    if args.demo:
        ph = DemoPhone()
        SA = demo_sa(ph)
    else:
        import sudoku_auto as SA
        try:
            import HIServices
            if not HIServices.AXIsProcessTrusted():
                sys.exit('Turn on Accessibility for Terminal (System Settings > Privacy & Security > Accessibility).')
        except ImportError:
            pass
        ph = SA.Phone(types.SimpleNamespace(delay=args.delay))

    holder = {}
    ui = MacUI(lambda m: holder['coach'].command(m), demo=args.demo)
    coach = Coach(args, ui, ph, SA)
    holder['coach'] = coach
    ui.lang_changed(coach.state['lang'])
    log(f'coach start: lang={coach.state["lang"]} placer={coach.state["placer"]} demo={args.demo}')
    threading.Thread(target=coach.run, daemon=True).start()
    ui.run()


if __name__ == '__main__':
    main()
