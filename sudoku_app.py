#!/usr/bin/env python3
"""sudoku_app.py - Sudoku Studio: one window for the iPhone Sudoku game (rule-based, no AI).

  Play   the autoplayer (sudoku_auto.Bot) finishes puzzles for you
  Learn  the coach (coach.Coach) explains one move at a time; you press Next
  Help   ready check with fixes, technique library on real boards, keys, troubleshooting

Only one of Play / Learn uses the phone at a time; starting one stops the other.
Run:  .venv/bin/python sudoku_app.py            (or double-click "Sudoku.command")
      .venv/bin/python sudoku_app.py --demo     (Learn and Help without the phone)
"""
import sys, os, re, time, json, threading, argparse, types, subprocess, traceback, queue

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import coach as K
import logic as L

WEB = os.path.join(HERE, 'web')
APP_SETTINGS = os.path.join(HERE, 'app_settings.json')
PLAY_LOG = os.path.join(HERE, 'sudoku_auto.log')
DELAY = {'safe': .12, 'fast': .07, 'turbo': .04}
SETTINGS_URL = {'settings_ax': 'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility',
                'settings_screen': 'x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture'}
GAME_DONE = re.compile(r'\*\*\* game (\d+)/(\d+) complete in (\d+)s')
NEW_PUZZLE = re.compile(r'new puzzle: (\d+) empty')
LEFT = re.compile(r', (\d+) left')


def log(m):
    K.log('[app] ' + m)


class LearnUI:
    """What the coach thinks is its window: forwards to the app."""
    def __init__(self, app):
        self.app = app

    def panel(self, state):
        self.app.learn_state(state)

    def overlay(self, data):
        self.app.ui.overlay(data)

    def lang_changed(self, lang):
        pass

    def close(self):
        self.app.learn_ended()


class App:
    def __init__(self, args):
        self.a = args
        st = K.load_json(APP_SETTINGS, {'lang': None, 'eastern': None, 'view': 'play',
                                         'play': {'games': 10, 'level': 'extreme', 'pattern': 'number', 'speed': 'fast',
                                                  'resume': True, 'popups': False},
                                         'learn_level': 'extreme'})
        coach_st = K.load_json(K.SETTINGS, {'lang': 'en', 'eastern': False, 'placer': 'coach', 'auto': False})
        self.lang = args.lang or st['lang'] or coach_st['lang']
        self.eastern = st['eastern'] if st['eastern'] is not None else coach_st['eastern']
        self.view = st['view'] if st['view'] in ('play', 'learn', 'help') else 'play'
        self.play_cfg = st['play']
        self.learn_level = st.get('learn_level', 'extreme')
        self.play_run = {'state': 'idle'}
        self.play_notice = None
        self.learn_notice = None
        self.bot_thread = None
        self.bot_flags = {'stop': False, 'paused': False}
        self.coach = None
        self.coach_thread = None
        self.learn = {}
        self.check = None
        self.ui = None
        self.cmdq = queue.Queue()
        threading.Thread(target=self.dispatch, daemon=True).start()
        self.hook_bot_log()

    def dispatch(self):
        """Commands from the window run one at a time, in the order you clicked."""
        while True:
            self.command(self.cmdq.get())

    # ------------------------------------------------------------ state to the window
    def save(self):
        K.save_json(APP_SETTINGS, {'lang': self.lang, 'eastern': self.eastern, 'view': self.view,
                                   'play': self.play_cfg, 'learn_level': self.learn_level})

    def learn_prefs(self):
        st = K.load_json(K.SETTINGS, {'placer': 'coach', 'auto': False})
        return {'placer': st['placer'], 'auto': bool(st['auto']), 'level': self.learn_level}

    def push(self, **only):
        state = {'lang': self.lang, 'eastern': self.eastern, 'view': self.view,
                 'play': {'cfg': self.play_cfg, 'run': self.play_run, 'notice': self.play_notice},
                 'learning': self.coach is not None, 'learn': self.learn, 'learnPrefs': self.learn_prefs(),
                 'learnNotice': self.learn_notice, 'check': self.check}
        if self.ui:
            self.ui.app_state(state)

    # ------------------------------------------------------------ commands from the window
    def command(self, m):
        cmd, v = m.get('cmd'), m.get('value')
        try:
            if cmd in ('ready', 'overlay_ready'):
                return self.push()
            if cmd == 'js_error':
                return log('screen error: ' + str(m.get('msg')))
            if cmd == 'quit':
                return self.quit()
            if cmd == 'view' and v in ('play', 'learn', 'help'):
                self.view = v
                self.save()
                self.push()
                if v == 'help':
                    self.run_check()
                return
            if cmd == 'lang':
                self.lang = 'ar' if self.lang == 'en' else 'en'
                self.save()
                if self.coach:
                    self.coach.command({'cmd': 'lang', 'value': self.lang})
                else:
                    self.set_coach_pref('lang', self.lang)
                self.ui.lang_changed(self.lang)
                return self.push()
            if cmd == 'eastern':
                self.eastern = bool(v)
                self.save()
                if self.coach:
                    self.coach.command({'cmd': 'eastern', 'value': self.eastern})
                else:
                    self.set_coach_pref('eastern', self.eastern)
                return self.push()
            if cmd == 'play_set':
                key = str(m.get('key'))
                if key in self.play_cfg and self.play_run['state'] not in ('running', 'paused', 'stopping'):
                    self.play_cfg[key] = v if key != 'games' else int(v)
                    self.save()
                return self.push()
            if cmd == 'play_start':
                return self.start_play()
            if cmd == 'play_pause':
                self.bot_flags['paused'] = not self.bot_flags['paused']
                self.play_run['state'] = 'paused' if self.bot_flags['paused'] else 'running'
                return self.push()
            if cmd == 'play_stop':
                self.bot_flags['stop'] = True
                self.play_run['state'] = 'stopping'
                return self.push()
            if cmd == 'learn_pref':
                key = str(m.get('key'))
                if key == 'level':
                    self.learn_level = str(v)
                    self.save()
                elif key in ('placer', 'auto'):
                    self.set_coach_pref(key, v)
                return self.push()
            if cmd == 'learn_start':
                return self.start_learn()
            if cmd == 'learn_stop':
                if self.coach:
                    self.coach.command({'cmd': 'quit'})
                return
            if cmd == 'check':
                return self.run_check()
            if cmd == 'fix':
                return self.fix(v)
            if cmd == 'open_log':
                path = PLAY_LOG if v == 'play' else K.LOGF
                subprocess.run(['open', path], capture_output=True)
                return
            if self.coach:                                   # everything else belongs to the lesson
                self.coach.command(m)
        except Exception:
            log('command failed: ' + traceback.format_exc())

    def set_coach_pref(self, key, value):
        st = K.load_json(K.SETTINGS, {})
        st[key] = value
        K.save_json(K.SETTINGS, st)

    # ------------------------------------------------------------ Play (autoplayer)
    def hook_bot_log(self):
        try:
            import sudoku_auto as SA
        except Exception:
            return
        orig = SA.log
        app = self

        def hooked(msg):
            orig(msg)
            app.on_bot_log(str(msg))
        SA.log = hooked
        SA.notify = lambda msg: None                          # the window shows it; no system sound

    def on_bot_log(self, msg):
        r = self.play_run
        if r.get('state') in (None, 'idle'):
            return
        r['activity'] = msg[:140]
        mt = GAME_DONE.search(msg)
        if mt:
            r.setdefault('results', []).append(int(mt.group(3)))
            r['done'] = int(mt.group(1))
            r['left'] = None
        mn = NEW_PUZZLE.search(msg)
        if mn:
            r['cells'] = int(mn.group(1))
            r['left'] = int(mn.group(1))
        ml = LEFT.search(msg)
        if ml:
            r['left'] = int(ml.group(1))

    def start_play(self):
        if self.a.demo:
            self.play_notice = {'key': 'demo_no_play', 'tone': 'warning'}
            return self.push()
        if self.bot_thread and self.bot_thread.is_alive():
            return
        if self.coach:
            self.coach.command({'cmd': 'quit'})
            if self.coach_thread:
                self.coach_thread.join(5)
            self.play_notice = {'key': 'mode_switched', 'tone': 'info'}
        else:
            self.play_notice = None
        cfg = dict(self.play_cfg)
        self.bot_flags = {'stop': False, 'paused': False}
        self.play_run = {'state': 'running', 'done': 0, 'total': cfg['games'], 'results': [], 'started': time.time(),
                         'elapsed': 0, 'activity': '', 'left': None, 'cells': 0}
        self.bot_thread = threading.Thread(target=self.play_worker, args=(cfg,), daemon=True)
        self.bot_thread.start()
        self.push()

    def play_worker(self, cfg):
        import sudoku_auto as SA
        r = self.play_run
        args = types.SimpleNamespace(games=cfg['games'], level=cfg['level'], pattern=cfg['pattern'],
                                     resume_open=bool(cfg['resume']), delay=DELAY.get(cfg['speed'], .07),
                                     max_wait=25, game_timeout=300, tap_single_button_popups=bool(cfg['popups']))
        finished = False
        try:
            K.check_permissions()
            bot = SA.Bot(args)
            SA.log(f'start: level={args.level} pattern={args.pattern} games={args.games} speed={cfg["speed"]}')
            bot.ph.ensure_front()
            last_push = 0
            while not self.bot_flags['stop']:
                if self.bot_flags['paused']:
                    time.sleep(0.15)
                else:
                    if bot.step():
                        finished = True
                        break
                now = time.time()
                r['elapsed'] = int(now - r['started'])
                r['gameElapsed'] = int(now - bot.t0)
                r['done'] = bot.done
                if now - last_push > 0.5:
                    last_push = now
                    self.push()
            r['state'] = 'done' if finished else 'stopped'
            SA.log(f'finished: {bot.done} game(s)' if finished else 'stopped by you')
            self.play_notice = None
        except SA.Stop as e:
            r['state'] = 'stopped'
            r['activity'] = str(e)[:200]
            self.play_notice = {'key': 'errors.' + K.error_kind(e), 'tone': 'error', 'text': str(e)}
            SA.log('STOPPED: ' + str(e))
        except Exception as e:
            r['state'] = 'stopped'
            r['activity'] = f'{type(e).__name__}: {e}'
            log('play error: ' + traceback.format_exc())
        r['elapsed'] = int(time.time() - r['started'])
        self.push()

    # ------------------------------------------------------------ Learn (coach)
    def start_learn(self):
        if self.coach:
            return
        if self.bot_thread and self.bot_thread.is_alive():
            self.bot_flags['stop'] = True
            self.bot_thread.join(8)
            self.learn_notice = {'key': 'learn_switched', 'tone': 'info'}
        else:
            self.learn_notice = None
        prefs = self.learn_prefs()
        args = types.SimpleNamespace(lang=self.lang, placer=prefs['placer'], speed=None, eastern=self.eastern,
                                     level=self.learn_level, delay=0.15, demo=self.a.demo)
        if self.a.demo:
            ph = K.DemoPhone()
            sa = K.demo_sa(ph)
        else:
            import sudoku_auto as sa
            try:
                K.check_permissions()
                ph = sa.Phone(types.SimpleNamespace(delay=0.15))
            except sa.Stop as e:
                self.learn_notice = {'key': 'errors.' + K.error_kind(e), 'tone': 'error', 'text': str(e)}
                self.view = 'help'
                self.push()
                return self.run_check()
        self.learn = {}
        self.coach = K.Coach(args, LearnUI(self), ph, sa)
        self.coach.state['lang'] = self.lang
        self.coach.state['eastern'] = self.eastern
        self.coach_thread = threading.Thread(target=self.coach.run, daemon=True)
        self.coach_thread.start()
        self.ui.show_overlay(True)
        self.push()

    def learn_state(self, state):
        self.learn = state
        self.push()

    def learn_ended(self):
        self.coach = None
        self.learn = {}
        self.ui.show_overlay(False)
        self.ui.overlay({'step': None})
        self.push()

    # ------------------------------------------------------------ Help: ready check and fixes
    def run_check(self):
        threading.Thread(target=self._check, daemon=True).start()

    def _check(self):
        res = {}
        try:
            import HIServices
            res['ax'] = {'ok': bool(HIServices.AXIsProcessTrusted())}
        except Exception:
            res['ax'] = {'ok': False}
        try:
            import Quartz
            res['screen'] = {'ok': bool(Quartz.CGPreflightScreenCaptureAccess())}
        except Exception:
            res['screen'] = {'ok': False}
        win = self.ui.phone_window() if self.ui else None
        res['window'] = {'ok': win is not None}
        res['board'] = {'ok': False}
        if win and res['screen']['ok']:
            try:
                import sudoku_auto as SA
                from PIL import Image
                path = '/tmp/sudoku_check.png'
                if subprocess.run(['screencapture', '-x', '-o', '-l', str(win[0]), path], capture_output=True).returncode == 0:
                    kind, _ = SA.classify(SA.arr(Image.open(path).convert('RGB')))
                    res['board'] = {'ok': kind == 'game', 'kind': kind}
            except Exception:
                log('check: ' + traceback.format_exc())
        if self.a.demo:
            res['board'] = {'ok': True, 'kind': 'game'} if not win else res['board']
        self.check = res
        self.push()

    def fix(self, what):
        if what == 'mirroring':
            subprocess.run(['open', '-a', 'iPhone Mirroring'], capture_output=True)
        elif what in SETTINGS_URL:
            try:
                if what == 'settings_ax':
                    import HIServices
                    HIServices.AXIsProcessTrustedWithOptions({HIServices.kAXTrustedCheckOptionPrompt: True})
                else:
                    import Quartz
                    Quartz.CGRequestScreenCaptureAccess()
            except Exception:
                pass
            subprocess.run(['open', SETTINGS_URL[what]], capture_output=True)
        threading.Timer(2.0, self.run_check).start()

    def quit(self):
        self.bot_flags['stop'] = True
        if self.coach:
            self.coach.command({'cmd': 'quit'})
        self.ui.stop()


# ================================================================ window (macOS)
class AppUI:
    def __init__(self, app, demo=False):
        import objc
        from AppKit import (NSApplication, NSWindow, NSPanel, NSColor, NSScreen, NSMakeRect,
                            NSBackingStoreBuffered, NSApplicationActivationPolicyAccessory)
        from Foundation import NSObject, NSURL, NSTimer
        from WebKit import WKWebView, WKWebViewConfiguration, WKUserContentController
        from PyObjCTools import AppHelper
        self.app, self.demo = app, demo
        self.AppHelper, self.NSMakeRect, self.NSScreen = AppHelper, NSMakeRect, NSScreen
        self.ready = {'app': False, 'overlay': False}
        self.pending_app = self.pending_overlay = None
        self.overlay_on = False
        self.lang = app.lang
        self.user_moved = False
        self.last_frame = None
        self.last_bounds = None
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        ui = self

        def plain(v):
            if isinstance(v, str):
                return str(v)
            if isinstance(v, bool) or v is None:
                return v
            if isinstance(v, (int, float)):
                return v
            try:
                return {str(k): plain(x) for k, x in dict(v).items()}
            except Exception:
                return str(v)

        class BookPanel(NSPanel):
            # a borderless window still takes keys (Next, Previous step, language)
            def canBecomeKeyWindow(self):
                return True

        class Bridge(NSObject, protocols=[objc.protocolNamed('WKScriptMessageHandler')]):
            def userContentController_didReceiveScriptMessage_(self, ucc, message):
                msg = plain(message.body())
                if msg.get('cmd') == 'drag':                 # move the book; runs right here on the main thread
                    return ui.drag(float(msg.get('dx', 0)), float(msg.get('dy', 0)))
                if msg.get('cmd') == 'ready':
                    ui.ready['app'] = True
                    ui.flush()
                if msg.get('cmd') == 'overlay_ready':
                    ui.ready['overlay'] = True
                    ui.flush()
                app.cmdq.put(msg)

        class Ticker(NSObject):
            def tick_(self, _t):
                ui.follow()

        class Closer(NSObject):
            def windowWillClose_(self, _n):
                app.quit()

        self.bridge, self.ticker, self.closer = Bridge.alloc().init(), Ticker.alloc().init(), Closer.alloc().init()

        def webview(frame, page):
            conf = WKWebViewConfiguration.alloc().init()
            ucc = WKUserContentController.alloc().init()
            ucc.addScriptMessageHandler_name_(self.bridge, 'coach')
            conf.setUserContentController_(ucc)
            wv = WKWebView.alloc().initWithFrame_configuration_(frame, conf)
            wv.setValue_forKey_(False, 'drawsBackground')
            wv.loadFileURL_allowingReadAccessToURL_(NSURL.fileURLWithPath_(os.path.join(WEB, page)), NSURL.fileURLWithPath_(WEB))
            wv.setAutoresizingMask_(18)
            return wv

        ov = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(NSMakeRect(0, 0, 339, 747), 0, NSBackingStoreBuffered, False)
        ov.setOpaque_(False)
        ov.setBackgroundColor_(NSColor.clearColor())
        ov.setHasShadow_(False)
        ov.setIgnoresMouseEvents_(True)
        ov.setLevel_(3)
        ov.setCollectionBehavior_(1 | 256)
        ov.setReleasedWhenClosed_(False)
        self.ov_web = webview(ov.contentView().bounds(), 'overlay.html')
        ov.contentView().addSubview_(self.ov_web)
        self.ov = ov

        h = min(860, int(NSScreen.mainScreen().visibleFrame().size.height) - 40)
        # the window is see-through and borderless: the page draws the book (spine, page edges, index tabs)
        win = BookPanel.alloc().initWithContentRect_styleMask_backing_defer_(NSMakeRect(0, 0, 440, h), 128,
                                                                             NSBackingStoreBuffered, False)
        win.setTitle_('Sudoku Studio')
        win.setOpaque_(False)
        win.setBackgroundColor_(NSColor.clearColor())
        win.setHasShadow_(False)
        win.setLevel_(3)
        win.setFloatingPanel_(True)
        win.setHidesOnDeactivate_(False)
        win.setBecomesKeyOnlyIfNeeded_(False)
        win.setCollectionBehavior_(1 | 256)
        win.setReleasedWhenClosed_(False)
        win.setDelegate_(self.closer)
        self.web = webview(win.contentView().bounds(), 'app.html')
        win.contentView().addSubview_(self.web)
        self.win = win
        self.follow(force=True)
        win.makeKeyAndOrderFront_(None)
        win.orderFrontRegardless()
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(0.3, self.ticker, 'tick:', None, True)

    def drag(self, dx, dy):
        f = self.win.frame()
        x, y = f.origin.x + dx, f.origin.y - dy
        self.win.setFrameOrigin_((x, y))
        self.user_moved = True
        self.last_frame = (x, y)

    # -------- phone window tracking
    def phone_window(self):
        from Quartz import CGWindowListCopyWindowInfo, kCGWindowListOptionOnScreenOnly, kCGNullWindowID
        wins = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID) or []
        mine = [w for w in wins if w.get('kCGWindowOwnerName') == 'iPhone Mirroring' and w.get('kCGWindowLayer', 1) == 0]
        if not mine:
            return None
        w = max(mine, key=lambda w: w['kCGWindowBounds']['Height'])
        b = w['kCGWindowBounds']
        return w['kCGWindowNumber'], (b['X'], b['Y'], b['Width'], b['Height'])

    def follow(self, force=False):
        pw = self.phone_window()
        b = pw[1] if pw else None
        main_h = self.NSScreen.screens()[0].frame().size.height
        scr = self.NSScreen.mainScreen().visibleFrame()
        if b is None and self.demo:
            k = min(1.0, (scr.size.height - 80) / 747)
            b = (scr.origin.x + scr.size.width / 2 - 339 * k - 20, 60, 339 * k, 747 * k)
        if b is not None and (force or b != self.last_bounds):
            X, Y, W, H = b
            self.ov.setFrame_display_(self.NSMakeRect(X, main_h - Y - H, W, H), True)
            self.last_bounds = b
            self.place_window(X, Y, W, H, main_h)
        elif b is None and force:
            self.win.center()
        visible = self.overlay_on and b is not None
        if visible and not self.ov.isVisible():
            self.ov.orderFrontRegardless()
        if not visible and self.ov.isVisible():
            self.ov.orderOut_(None)

    def place_window(self, X, Y, W, H, main_h):
        cur = self.win.frame()
        if self.last_frame and (abs(cur.origin.x - self.last_frame[0]) > 2 or abs(cur.origin.y - self.last_frame[1]) > 2):
            self.user_moved = True
        if self.user_moved:
            return
        scr = self.NSScreen.mainScreen().visibleFrame()
        pw, ph = cur.size.width, cur.size.height
        right, left = X + W + 2, X - pw - 2
        fits_r, fits_l = right + pw <= scr.origin.x + scr.size.width, left >= scr.origin.x
        x = (left if fits_l else right) if self.lang == 'ar' else (right if fits_r else left)
        if not (fits_l or fits_r):
            x = scr.origin.x + scr.size.width - pw
        y = max(scr.origin.y, min(main_h - Y - ph, scr.origin.y + scr.size.height - ph))
        self.win.setFrameOrigin_((x, y))
        self.last_frame = (x, y)

    # -------- thread-safe calls
    def js(self, wv, code):
        wv.evaluateJavaScript_completionHandler_(code, None)

    def flush(self):
        if self.ready['app'] and self.pending_app:
            self.js(self.web, 'app.update(%s)' % self.pending_app)
        if self.ready['overlay'] and self.pending_overlay:
            self.js(self.ov_web, 'overlay.render(%s)' % self.pending_overlay)

    def app_state(self, state):
        data = json.dumps(state, ensure_ascii=False, default=str)
        def go():
            self.pending_app = data
            if self.ready['app']:
                self.js(self.web, 'app.update(%s)' % data)
        self.AppHelper.callAfter(go)

    def overlay(self, d):
        data = json.dumps(d, ensure_ascii=False, default=str)
        def go():
            self.pending_overlay = data
            if self.ready['overlay']:
                self.js(self.ov_web, 'overlay.render(%s)' % data)
        self.AppHelper.callAfter(go)

    def show_overlay(self, on):
        def go():
            self.overlay_on = on
            self.follow()
        self.AppHelper.callAfter(go)

    def lang_changed(self, lang):
        def go():
            self.lang = lang
            if self.last_bounds:
                self.place_window(*self.last_bounds, self.NSScreen.screens()[0].frame().size.height)
        self.AppHelper.callAfter(go)

    def stop(self):
        self.AppHelper.callAfter(self.AppHelper.stopEventLoop)

    def run(self):
        self.AppHelper.runEventLoop(installInterrupt=True)


def main():
    ap = argparse.ArgumentParser(description='Sudoku Studio - Play, Learn and Help in one window.')
    ap.add_argument('--lang', choices=['en', 'ar'])
    ap.add_argument('--demo', action='store_true', help='Learn and Help without the phone')
    args = ap.parse_args()
    app = App(args)
    app.ui = AppUI(app, demo=args.demo)
    log(f'studio start: lang={app.lang} demo={args.demo}')
    app.ui.run()


if __name__ == '__main__':
    main()
