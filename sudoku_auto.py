#!/usr/bin/env python3
"""sudoku_auto.py v2 - plays Sudoku on your iPhone through Mac "iPhone Mirroring". Rule-based, no AI.

Every step:  screenshot -> recognise the screen -> act on it -> screenshot again.
  game     : read board (pixel templates), check it twice, require a UNIQUE solution,
             enter one digit group, re-read (catches dropped taps / wrong digits / pop-ups)
  complete : find the "New Game" button and tap it
  sheet    : find the level rows in the sheet and tap your level
  home     : tap the blue "New Game" button
  popup    : two choices -> tap the secondary one (Later / No thanks); one button -> stop
  unknown  : wait, then stop with a screenshot (never taps blindly)
Safety: pauses if you move the mouse, re-focuses iPhone Mirroring before tapping,
        stops if the same tap does not change the screen, logs to sudoku_auto.log next to this
        script, saves problem screenshots to debug/ next to this script.

Setup:  pip install -r requirements.txt
        Terminal needs "Screen Recording" + "Accessibility" (System Settings > Privacy & Security)
Run:    python3 sudoku_auto.py --dry-run                 # what it sees + tap map, no taps
        python3 sudoku_auto.py --games 10 --level extreme
"""
import sys, os, time, argparse, signal, subprocess
import numpy as np
from PIL import Image

N = 16
CENT="000000013468997700012468999999993468999988899999999987543357999955432110014799990000000001479999000000000147999900000000014799990000000001479999000000000147999900000000014799990000000001479999000000000147999900000000014799990000000001479999000000000136999800024799986310000259998889998410379974222358984089861000000389726641000000017984000000000001898400000000001499610000000002599730000000003799620000000025998510000000047996300000000268984100000001489862000000003689962112211210899998888888887689999999999999980012589999752000026999878899951027996311124799506995100000038971243100000001897300000000000489610000012224699730000017999999830000001577788997300000000000148984000000000000489955410000000038998984000000016998479853211236997303699988889996200013689999852000000000000389610000000000389972000000000389997200000000289889720000000279627972000000279720797200000379720079720000279830007972000279720000797200179730000179730079986555569997548999999999999998333333333489853200000000007972000000000000797200000000000059720016999999999999603799877777777750589720000000000068850000000000006884000000000000698413466552000089988899999873008999864324799950888610000002898611100000000048990000000000003799453000000000389999840000000279865898532111479961037999888899952000126899998520000000258999852000002599887889852002699631113799611698500000015872389610000000022058840134554200007986689999996300899998644469984099996100000279848996100000003898699600000000269948961000000037991798400000016985037986311236996100269988888996200001368999862000689999999999998688888888888999991222222222359985000000000015996100000000004997300000000003799400000000001699610000000000589810000000000289830000000000279950000000000159962000000000048983000000000027994100000000006997100000000014897200000000001598400000000000036799998620000159987667899410169962100026995037961000000169733785000000005973169720000002797202698532235897300037999999998300036998666789973037973000000279738972000000003798996100000000179979730000000037973797421001247984026998777789963000026899987631000013699998531000026998777899620027986310125897306885000000048961897200000001698399610000000069978973000000017998489720000026999905899643469999980037999999855797000023454310488512100000000169723785100000158950169962111369961002599888889851000002479997510000"

APP = 'iPhone Mirroring'
XS = [30, 65, 100, 134, 169, 204, 239, 273, 308]   # cell centres (339x747 reference frame)
YS = [189, 224, 259, 294, 329, 364, 399, 434, 469]
PAD_Y = 610
def padx(v): return 33 + 34 * (v - 1)

# =============================================================== screen recognition
RW,RH=339,747
GRID=(12,170,327,488)
LEVELS=['easy','medium','hard','expert','master','extreme']
PATTERNS=['number','row','column','box','snake']
def arr(im): return np.asarray(im.convert('RGB'),dtype=float)
def Y(a,fy): return int(fy*a.shape[0]/RH)
def X(a,fx): return int(fx*a.shape[1]/RW)
def reg(a,x0,y0,x1,y1): return a[Y(a,y0):max(Y(a,y1),Y(a,y0)+1), X(a,x0):max(X(a,x1),X(a,x0)+1)]
def runs(m):
    out=[];s=None
    for i,v in enumerate(m):
        if v and s is None: s=i
        if not v and s is not None: out.append((s,i-1)); s=None
    if s is not None: out.append((s,len(m)-1))
    return out
def to_f(a,py): return py*RH/a.shape[0]
def blue_mask(p): return (p[...,2]>180)&(p[...,0]<110)&(p[...,2]-p[...,0]>90)
def white_mask(p): return p.min(-1)>220
def card(a, xfrac=.12):
    """Tallest bright run in a column near the left edge -> (top,bottom) in frame px."""
    col=a[:,int(a.shape[1]*xfrac)]
    best=None
    for s,e in runs(col.min(1)>215):
        if best is None or e-s>best[1]-best[0]: best=(s,e)
    return (to_f(a,best[0]),to_f(a,best[1])) if best else (0,0)
def is_dimmed_above(a,top):
    p=reg(a,100,max(0,top-30),240,max(1,top-4)); return p.size and p.mean()<200
def sheet_rows(a):
    """Level sheet (white card glued to the bottom). Returns {level: y} or None."""
    top,bot=card(a)
    if not (bot>RH*.9 and 250<top<RH*.75 and bot-top>RH*.3 and is_dimmed_above(a,top)): return None
    ink=(reg(a,85,top,255,bot).min(-1)<190).mean(1)>.02
    centres=[top+to_f(a,(s+e)/2) for s,e in runs(ink)]
    out={}
    for i,lv in enumerate(LEVELS):
        guess=top+23+i*48.5
        near=[c for c in centres if abs(c-guess)<14]
        out[lv]=min(near,key=lambda c:abs(c-guess)) if near else guess
    return out
def pill(a, y0, y1, mask, frac=.6, x0=60, x1=280, bottom=False):
    """Wide horizontal button band (blue or white) between frame y0..y1 -> centre y (and bottom) or None."""
    p=reg(a,x0,y0,x1,y1); m=mask(p).mean(1)>frac
    bs=[b for b in runs(m) if to_f(a,b[1]-b[0])>=8]
    if not bs: return None
    b=max(bs,key=lambda t:t[1]-t[0]); c=y0+to_f(a,(b[0]+b[1])/2)
    return (c,y0+to_f(a,b[1])) if bottom else c
def popup(a):
    """Centered dialog card (not glued to bottom) over a dimmed screen.
    Returns ('two', primary_y, secondary_y) / ('one', primary_y, None) or None."""
    rows=(reg(a,60,0,280,RH).min(-1)>215).mean(1)>.6
    rs=runs(rows); merged=[]
    for r in rs:
        if merged and to_f(a,r[0]-merged[-1][1])<60: merged[-1]=(merged[-1][0],r[1])
        else: merged.append(r)
    if not merged: return None
    b=max(merged,key=lambda t:t[1]-t[0]); top,bot=to_f(a,b[0]),to_f(a,b[1])
    if not (bot<RH*.88 and top>60 and bot-top>RH*.2 and is_dimmed_above(a,top)): return None
    r=pill(a,top,bot,blue_mask,.5,90,250,bottom=True)
    if r is None: return None
    py,pb=r
    # pill edge is anti-aliased: skip until rows are clean again, then look for a text link
    sub=reg(a,110,pb,230,bot+2); clean=(sub.min(-1)>215).mean(1)>.97
    k=next((i for i,v in enumerate(clean) if v),None)
    sec=None
    if k is not None:
        y0=pb+to_f(a,k)
        rs=runs((reg(a,110,y0,230,bot+2).min(-1)<200).mean(1)>.03)
        if rs: sec=y0+to_f(a,(rs[0][0]+rs[0][1])/2)
    return ('two',py,sec) if sec else ('one',py,None)
def is_game(a):
    hdr=reg(a,20,100,320,160); board=reg(a,*GRID)
    if hdr.mean()<210 or board.mean()<150: return False
    # thick box separators: darker vertical lines at 1/3 and 2/3 of the board
    g=board.mean(-1); w=g.shape[1]
    med=np.median(g)
    lines=[g[:,int(w*f)-2:int(w*f)+3].min(1).mean() for f in (1/3,2/3)]
    return all(l<228 and med-l>18 for l in lines)
def classify(a):
    """-> (state, info)"""
    if is_game(a): return 'game',None
    r=sheet_rows(a)
    if r: return 'sheet',r
    p=popup(a)
    if p: return 'popup',p
    blue=blue_mask(a).mean()
    if blue>.25:
        b=pill(a,520,720,white_mask,.6)
        if b: return 'complete',b
    else:
        b=pill(a,480,700,blue_mask,.6)
        if b and reg(a,0,0,339,747).mean()>170: return 'home',b
    return 'other',None
# =============================================================== board OCR (pixel templates, no AI)
T = np.array([int(ch) / 10 + 0.05 for ch in CENT]).reshape(9, N * N)

def crop_grid(im):
    w, h = im.size
    x0, y0, x1, y1 = GRID
    return im.crop((int(x0 * w / RW), int(y0 * h / RH), int(x1 * w / RW), int(y1 * h / RH)))

def read(grid_img):
    im = np.asarray(grid_img.convert('L'), dtype=float)
    h, w = im.shape
    g = []
    for r in range(9):
        s = ''
        for c in range(9):
            cell = im[int(h * r / 9):int(h * (r + 1) / 9), int(w * c / 9):int(w * (c + 1) / 9)]
            m = int(min(cell.shape) * .15)
            cell = cell[m:-m, m:-m]
            ink = (np.median(cell) - cell) > 60
            ys, xs = np.nonzero(ink)
            if len(ys) < max(8, ink.size // 150):
                s += '.'
                continue
            cr = ink[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(np.uint8) * 255
            f = np.asarray(Image.fromarray(cr).resize((N, N), Image.BILINEAR), dtype=float).ravel() / 255
            s += str(1 + int(np.argmin(((T - f) ** 2).sum(1))))
        g.append(s)
    return g

def original_clues(grid_img, g):
    """Keep black given digits and ignore blue player-entered digits."""
    rgb = np.asarray(grid_img.convert('RGB'))
    h, w = rgb.shape[:2]
    out = []
    for r in range(9):
        row = ''
        for c in range(9):
            digit = g[r][c]
            if digit == '.':
                row += '.'
                continue
            cell = rgb[int(h*r/9):int(h*(r+1)/9), int(w*c/9):int(w*(c+1)/9)]
            margin = int(min(cell.shape[:2]) * .15)
            cell = cell[margin:-margin, margin:-margin]
            gray = np.asarray(Image.fromarray(cell).convert('L'), dtype=float)
            ink = (np.median(gray) - gray) > 60
            blue = ink & ((cell[..., 2].astype(int) - cell[..., 0].astype(int)) > 35)
            row += '.' if ink.any() and blue.sum() / ink.sum() > .35 else digit
        out.append(row)
    return out

def valid(g):
    for k in range(9):
        for cells in ([g[k][c] for c in range(9)], [g[r][k] for r in range(9)],
                      [g[k // 3 * 3 + i][k % 3 * 3 + j] for i in range(3) for j in range(3)]):
            d = [x for x in cells if x != '.']
            if len(d) != len(set(d)):
                return False
    return sum(r.count('.') for r in g) <= 64

# =============================================================== solver (bitmask MRV, counts solutions)
def solve(g, limit=2):
    """Returns (number_of_solutions_found_up_to_limit, first_solution)."""
    cells = [0 if ch == '.' else int(ch) for r in g for ch in r]
    rows, cols, boxes = [0] * 9, [0] * 9, [0] * 9
    for i, v in enumerate(cells):
        if v:
            b = 1 << v; r, c = divmod(i, 9); x = r // 3 * 3 + c // 3
            if rows[r] & b or cols[c] & b or boxes[x] & b:
                return 0, None
            rows[r] |= b; cols[c] |= b; boxes[x] |= b
    found = [0, None]
    def rec():
        best, bm, bn = -1, 0, 10
        for i in range(81):
            if not cells[i]:
                r, c = divmod(i, 9)
                m = ~(rows[r] | cols[c] | boxes[r // 3 * 3 + c // 3]) & 0x3FE
                n = bin(m).count('1')
                if n < bn:
                    best, bm, bn = i, m, n
                    if n <= 1:
                        break
        if best < 0:
            found[0] += 1
            if found[1] is None:
                found[1] = [''.join(map(str, cells[k * 9:k * 9 + 9])) for k in range(9)]
            return found[0] >= limit
        r, c = divmod(best, 9); x = r // 3 * 3 + c // 3
        for v in range(1, 10):
            b = 1 << v
            if bm & b:
                cells[best] = v; rows[r] |= b; cols[c] |= b; boxes[x] |= b
                if rec():
                    return True
                cells[best] = 0; rows[r] &= ~b; cols[c] &= ~b; boxes[x] &= ~b
        return False
    rec()
    return found[0], found[1]

def fill_group(blanks, sol, pattern):
    """Return the next visible group of cells in the selected fill pattern."""
    if pattern == 'number':
        digit = min(int(sol[r][c]) for r, c in blanks)
        cells = [(r, c) for r, c in blanks if int(sol[r][c]) == digit]
    elif pattern in ('row', 'snake'):
        row = min(r for r, _c in blanks)
        cells = [(r, c) for r, c in blanks if r == row]
        if pattern == 'snake' and row % 2:
            cells.reverse()
    elif pattern == 'column':
        column = min(c for _r, c in blanks)
        cells = [(r, c) for r, c in blanks if c == column]
    else:
        box = min(r // 3 * 3 + c // 3 for r, c in blanks)
        cells = [(r, c) for r, c in blanks if r // 3 * 3 + c // 3 == box]
    return [(int(sol[r][c]), r, c) for r, c in cells]

def puzzle_changed(clues, sol):
    return sum(clues[r][c] != '.' and clues[r][c] != sol[r][c]
               for r in range(9) for c in range(9)) >= 2

# =============================================================== Mac side: window, capture, taps
class Stop(Exception):
    pass

class Phone:
    def __init__(self, args):
        self.args = args
        self.last_tap = None
        self.refresh()

    def refresh(self):
        from Quartz import CGWindowListCopyWindowInfo, kCGWindowListOptionOnScreenOnly, kCGNullWindowID
        wins = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID)
        mine = [w for w in wins if w.get('kCGWindowOwnerName') == APP and w.get('kCGWindowLayer', 1) == 0]
        if not mine:
            raise Stop(f'"{APP}" window not found - open iPhone Mirroring and unlock the phone.')
        w = max(mine, key=lambda w: w['kCGWindowBounds']['Height'])
        b = w['kCGWindowBounds']
        self.wid = w['kCGWindowNumber']
        self.bounds = (b['X'], b['Y'], b['Width'], b['Height'])
        front = next((x for x in wins if x.get('kCGWindowLayer', 1) == 0), None)
        self.frontmost = bool(front) and front.get('kCGWindowOwnerName') == APP

    def ensure_front(self):
        self.refresh()
        for _ in range(3):
            if self.frontmost:
                return
            subprocess.run(['osascript', '-e', f'tell application "{APP}" to activate'], capture_output=True)
            time.sleep(0.7)
            self.refresh()
        raise Stop('Could not bring iPhone Mirroring to the front.')

    def shot(self, path='/tmp/sudoku_ss.png'):
        r = subprocess.run(['screencapture', '-x', '-o', '-l', str(self.wid), path], capture_output=True)
        if r.returncode != 0:
            self.refresh()
            r = subprocess.run(['screencapture', '-x', '-o', '-l', str(self.wid), path], capture_output=True)
            if r.returncode != 0:
                raise Stop('Screenshot failed - give Terminal "Screen Recording" permission.')
        return Image.open(path).convert('RGB')

    def stable_shot(self, tries=6):
        """Two captures 0.3 s apart that match -> no animation in progress."""
        a = self.shot()
        for i in range(tries):
            time.sleep(0.3)
            b = self.shot('/tmp/sudoku_ss2.png')
            sa = np.asarray(a.convert('L').resize((68, 150)), dtype=float)
            sb = np.asarray(b.convert('L').resize((68, 150)), dtype=float)
            if np.abs(sa - sb).mean() < 1.5:
                return b, True, a
            if i == tries - 1:
                return b, False, a
            a = b

    def _mouse(self):
        from Quartz import CGEventGetLocation, CGEventCreate
        p = CGEventGetLocation(CGEventCreate(None))
        return p.x, p.y

    def guard_mouse(self):
        """If the user moved the mouse since our last tap, pause until it has been still for 3 s."""
        if self.last_tap is None:
            return
        x, y = self._mouse()
        if abs(x - self.last_tap[0]) + abs(y - self.last_tap[1]) <= 4:
            return
        log('mouse moved by you -> paused (leave the mouse still for 3 s to resume, Ctrl-C to quit)')
        still, pos = 0, (x, y)
        while still < 3:
            time.sleep(0.5)
            now = self._mouse()
            still = still + 0.5 if now == pos else 0
            pos = now
        self.last_tap = None
        self.ensure_front()
        log('resumed')

    def tap(self, fx, fy, pause=None):
        from Quartz import (CGEventCreateMouseEvent, CGEventPost, kCGHIDEventTap,
                            kCGEventLeftMouseDown, kCGEventLeftMouseUp, kCGMouseButtonLeft)
        self.guard_mouse()
        X, Yb, W, H = self.bounds
        p = (X + fx * W / RW, Yb + fy * H / RH)
        for t in (kCGEventLeftMouseDown, kCGEventLeftMouseUp):
            CGEventPost(kCGHIDEventTap, CGEventCreateMouseEvent(None, t, p, kCGMouseButtonLeft))
            time.sleep(0.03)
        self.last_tap = p
        time.sleep(self.args.delay if pause is None else pause)

# =============================================================== helpers
def close(i1, i2, tol=5):
    if isinstance(i1, dict):
        return all(abs(i1[k] - i2[k]) < tol for k in i1)
    if isinstance(i1, tuple):
        return i1[0] == i2[0] and all((x is None and y is None) or (x is not None and y is not None and abs(x - y) < tol)
                                      for x, y in zip(i1[1:], i2[1:]))
    return i1 is not None and i2 is not None and abs(i1 - i2) < tol

HERE = os.path.dirname(os.path.abspath(__file__))
LOGF = os.path.join(HERE, 'sudoku_auto.log')
DBG = os.path.join(HERE, 'debug')

def log(m):
    line = time.strftime('%H:%M:%S ') + m
    print(line, flush=True)
    try:
        with open(LOGF, 'a') as f:
            f.write(line + '\n')
    except OSError:
        pass

def save_debug(im, tag):
    os.makedirs(DBG, exist_ok=True)
    p = os.path.join(DBG, time.strftime('%Y%m%d-%H%M%S-') + tag + '.png')
    im.save(p)
    return p

def notify(msg):
    subprocess.run(['osascript', '-e', f'display notification "{msg}" with title "Sudoku bot"'], capture_output=True)
    subprocess.run(['afplay', '/System/Library/Sounds/Funk.aiff'], capture_output=True)

def show(g):
    return '\n'.join(' '.join(r) for r in g)

# =============================================================== the bot (state machine)
class Bot:
    def __init__(self, args):
        self.a = args
        self.ph = Phone(args)
        self.done = 0
        self.new_game()
        self.since = time.time()       # time the current "waiting" state started
        self.state_taps = {}           # how many times we tapped while in a navigation state

    def new_game(self):
        self.sol = None
        self.played = False            # we entered at least one digit in this game
        self.tries = {}                # (r,c) -> how many times we tapped it
        self.misreads = 0
        self.stall, self.last_left = 0, 99
        self.t0 = time.time()

    def wait(self, why, im):
        elapsed = time.time() - self.since
        if elapsed > self.a.max_wait:
            p = save_debug(im, why.split()[0])
            raise Stop(f'{why} for {self.a.max_wait}s - stopped without tapping. Screenshot: {p}')
        waiting = (why, int(elapsed // 2))
        if waiting != getattr(self, 'last_waiting', None):
            log(f'waiting: {why} ({elapsed:.0f}s)')
            self.last_waiting = waiting
        time.sleep(0.6)

    def nav_tap(self, state, x, y, label):
        n = self.state_taps.get(state, 0) + 1
        self.state_taps[state] = n
        if n > 6:
            raise Stop(f'tapped "{label}" {n - 1} times but the screen did not change - stopped.')
        log(f'{state}: tap {label}')
        self.ph.tap(x, y, pause=1.2)

    def step(self):
        im, stable, prev = self.ph.stable_shot(tries=3)
        a = arr(im)
        state, info = classify(a)
        if state not in ('game', 'other') and not stable:
            # confetti etc. never stops moving: accept the screen if both shots agree on what to tap
            s2, i2 = classify(arr(prev))
            stable = s2 == state and close(info, i2)
        if state != getattr(self, 'last_state', None):
            self.since = time.time()
            self.state_taps = {}
            self.last_state = state
            self.last_waiting = None
            log(f'sees: {state}')

        if state == 'game':
            return self.play(im, stable)
        if not stable:
            return self.wait('screen kept animating', im)
        if state == 'complete':
            if self.played:
                self.done += 1
                log(f'*** game {self.done}/{self.a.games} complete in {time.time() - self.t0:.0f}s')
                self.new_game()
            if self.done >= self.a.games:
                return True
            self.ph.ensure_front()
            return self.nav_tap('complete', 170, info, 'New Game')
        if state == 'sheet':
            self.ph.ensure_front()
            return self.nav_tap('sheet', 170, info[self.a.level], self.a.level.capitalize())
        if state == 'home':
            self.ph.ensure_front()
            return self.nav_tap('home', 170, info, 'New Game')
        if state == 'popup':
            kind, py, sy = info
            if kind == 'two':
                self.ph.ensure_front()
                return self.nav_tap('popup', 170, sy, 'secondary option (Later / No thanks)')
            if self.a.tap_single_button_popups:
                self.ph.ensure_front()
                return self.nav_tap('popup', 170, py, 'the only button (e.g. Collect)')
            p = save_debug(im, 'popup')
            raise Stop(f'pop-up with a single button - not tapped (use --tap-single-button-popups). Screenshot: {p}')
        return self.wait('unknown screen', im)

    def play(self, im, stable):
        grid = crop_grid(im)
        g = read(grid)
        clues = original_clues(grid, g) if self.a.resume_open else g
        if not stable or not valid(clues):
            return self.wait('board covered (toast / animation)', im)
        g2 = read(crop_grid(self.ph.shot()))
        if g2 != g:
            return self.wait('board changing', im)
        filled = [(r, c) for r in range(9) for c in range(9) if g[r][c] != '.']
        if self.sol is not None:
            wrong = [(r, c) for r, c in filled if g[r][c] != self.sol[r][c]]
            if len(wrong) > 3 or (self.a.resume_open and puzzle_changed(clues, self.sol)):
                log(f'board does not match the saved solution ({len(wrong)} cells) -> treating as a new puzzle')
                self.new_game()
        if self.sol is None:
            n, s = solve(clues)
            if n != 1:
                self.misreads += 1
                if self.misreads >= 8:
                    p = save_debug(im, 'unreadable')
                    raise Stop(f'board read gives {n} solutions (OCR problem) - stopped. Screenshot: {p}\n{show(g)}')
                log(f'board read gives {n} solutions - re-reading')
                return time.sleep(0.8)
            self.sol = s
            self.misreads = 0
            ignored = sum(row.count('.') for row in clues) - sum(row.count('.') for row in g)
            if ignored:
                log(f'resume: checking {ignored} existing player-entered cell(s) against original clues')
            log(f'new puzzle: {sum(r.count(".") for r in g)} empty cells, unique solution found')
        sol = self.sol
        wrong = [(r, c) for r, c in filled if g[r][c] != sol[r][c]]
        blanks = [(r, c) for r in range(9) for c in range(9) if g[r][c] == '.']
        if not blanks and not wrong:
            if time.time() - self.since > 25:
                p = save_debug(im, 'full-board')
                raise Stop(f'board is full but the result screen never came - check the phone. Screenshot: {p}')
            return time.sleep(0.6)
        # fix wrong digits first (a dropped tap can put a digit in the previously selected cell)
        todo = []
        for r, c in wrong:
            k = (r, c)
            if self.tries.get(k, 0) >= 2:
                continue                       # probably an OCR misread of a correct digit - leave it
            todo.append((int(sol[r][c]), r, c))
        if wrong and not todo and not blanks:
            p = save_debug(im, 'wrong-cells')
            raise Stop(f'cells {wrong} still differ after 2 fixes - stopped. Screenshot: {p}')
        if not todo:
            # one visible group per round, then look again (catches pop-ups and dropped taps quickly)
            todo = fill_group(blanks, sol, self.a.pattern)
        # stall guard: the number of empty cells must keep going down
        left = len(blanks) + len(wrong)
        self.stall = self.stall + 1 if left >= getattr(self, 'last_left', 99) else 0
        self.last_left = left
        if self.stall >= 5:
            p = save_debug(im, 'stuck')
            raise Stop(f'no progress in 5 rounds ({left} cells left; Notes mode on? board blocked?) '
                       f'- stopped. Screenshot: {p}')
        for v, r, c in todo:
            k = (r, c)
            self.tries[k] = self.tries.get(k, 0) + 1
        self.ph.ensure_front()
        for v, r, c in todo:
            self.ph.tap(XS[c], YS[r], pause=self.a.delay)
            self.ph.tap(padx(v), PAD_Y, pause=self.a.delay)
        self.played = True
        self.since = time.time()
        if time.time() - self.t0 > self.a.game_timeout:
            raise Stop(f'game took more than {self.a.game_timeout}s - stopped.')
        log(f'entered {len(todo)} cell(s)' + (f' (fixed {len(wrong)})' if wrong else f' by {self.a.pattern}')
            + f', {len(blanks) - (0 if wrong else len(todo))} left')

    def run(self):
        log(f'start: level={self.a.level} pattern={self.a.pattern} resume={self.a.resume_open} '
            f'games={self.a.games} window={self.ph.bounds}')
        self.ph.ensure_front()
        self.paused = False
        signal.signal(signal.SIGUSR1, lambda *_: setattr(self, 'paused', not self.paused))
        while True:
            if self.paused:
                time.sleep(0.1)
            elif self.step():
                break
        log(f'finished: {self.done} game(s)')
        notify(f'Finished {self.done} game(s)')

def dry_run(args):
    ph = Phone(args)
    im, stable, _ = ph.stable_shot()
    a = arr(im)
    state, info = classify(a)
    log(f'window {ph.bounds}, frontmost={ph.frontmost}, stable={stable}, screen={state}, info={info}')
    # annotated picture of every point the bot would tap
    from PIL import ImageDraw
    w, h = im.size
    d = ImageDraw.Draw(im)
    def dot(fx, fy, col):
        x, y = fx * w / RW, fy * h / RH
        d.ellipse((x - 5, y - 5, x + 5, y + 5), outline=col, width=3)
    for y in YS:
        for x in XS:
            dot(x, y, 'red')
    for v in range(1, 10):
        dot(padx(v), PAD_Y, 'green')
    if state == 'sheet':
        for lv, y in info.items():
            dot(170, y, 'magenta')
    elif state in ('complete', 'home'):
        dot(170, info, 'magenta')
    elif state == 'popup':
        dot(170, info[1], 'magenta')
        if info[2]:
            dot(170, info[2], 'orange')
    p = save_debug(im, 'dry-run')
    log(f'tap map saved: {p}')
    if state == 'game':
        g = read(crop_grid(ph.shot()))
        print(show(g))
        n, s = solve(g)
        print(f'\nsolutions found: {n} (must be 1)')
        if s:
            print(show(s))

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Auto-play Sudoku on iPhone Mirroring (rule-based, no AI).')
    ap.add_argument('--games', type=int, default=10)
    ap.add_argument('--level', default='extreme', choices=LEVELS)
    ap.add_argument('--pattern', default='number', choices=PATTERNS)
    ap.add_argument('--resume-open', action='store_true', help='solve from black clues and repair blue entries')
    ap.add_argument('--delay', type=float, default=0.12, help='seconds after each tap (raise if taps get dropped)')
    ap.add_argument('--max-wait', type=int, default=25, help='seconds to wait on an unknown/blocked screen before stopping')
    ap.add_argument('--game-timeout', type=int, default=300)
    ap.add_argument('--tap-single-button-popups', action='store_true',
                    help='also tap pop-ups that have only one button (e.g. "Collect"). Off by default for safety.')
    ap.add_argument('--dry-run', action='store_true', help='show what it sees and where it would tap; no taps')
    args = ap.parse_args()
    try:
        if args.dry_run:
            dry_run(args)
        else:
            try:
                import HIServices
                if not HIServices.AXIsProcessTrusted():
                    raise Stop('Clicks are blocked: turn on Accessibility for Terminal '
                               '(System Settings > Privacy & Security > Accessibility), restart Terminal.')
            except ImportError:
                pass
            Bot(args).run()
    except Stop as e:
        log('STOPPED: ' + str(e))
        notify('Stopped - see Terminal')
        sys.exit(1)
    except KeyboardInterrupt:
        log('stopped by you (Ctrl-C)')
