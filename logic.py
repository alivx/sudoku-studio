#!/usr/bin/env python3
"""logic.py - human-style Sudoku step finder for the training coach. No AI, no guessing.

next_step(board, cands, sol) returns the easiest logical step a person would find next,
as a plain dict the overlay can draw and the panel can explain:

  tech     technique key (see TECHS)          tier   1 (basic) .. 5 (beyond the coach)
  place    [cell, digit] or None              elim   [[cell, digit], ...]
  units    unit ids to spotlight              pattern key cells (purple)
  sources  cells holding digits that do the work (coral)
  beams    [[from_cell, to_cell], ...]        blocked [[cell, source_or_None], ...]
  links    [[cell, cell, 'strong'|'weak'], ...]
  marks    [[cell, digit, 'keep'|'elim'|'cand'], ...]   small candidate digits to draw
  target   cell the answer goes in (or None)  p      parameters for the text templates

Cells are 0..80 (row*9+col). Units: 0-8 rows, 9-17 columns, 18-26 boxes.
Every step is checked against the full solution before it is returned, so a bug in a
detector can never teach a wrong move.
"""
from itertools import combinations

ROWS = [[r * 9 + c for c in range(9)] for r in range(9)]
COLS = [[r * 9 + c for r in range(9)] for c in range(9)]
BOXES = [[(b // 3 * 3 + i) * 9 + b % 3 * 3 + j for i in range(3) for j in range(3)] for b in range(9)]
UNITS = ROWS + COLS + BOXES
KIND = ['row'] * 9 + ['col'] * 9 + ['box'] * 9


def R(i): return i // 9
def C(i): return i % 9
def B(i): return i // 27 * 3 + i % 9 // 3


UNITS_OF = [(R(i), 9 + C(i), 18 + B(i)) for i in range(81)]
PEERS = [set(UNITS[R(i)]) | set(UNITS[9 + C(i)]) | set(UNITS[18 + B(i)]) for i in range(81)]
for _i in range(81):
    PEERS[_i].discard(_i)

TECHS = ['mistake', 'full_house', 'hidden_single', 'naked_single',
         'pointing', 'claiming', 'naked_pair', 'hidden_pair',
         'naked_triple', 'hidden_triple', 'x_wing', 'xy_wing', 'skyscraper', 'kite',
         'swordfish', 'reveal']
TIER = {'mistake': 0, 'full_house': 1, 'hidden_single': 1, 'naked_single': 1,
        'pointing': 2, 'claiming': 2, 'naked_pair': 2, 'hidden_pair': 2,
        'naked_triple': 3, 'hidden_triple': 3, 'x_wing': 3, 'xy_wing': 3, 'skyscraper': 3, 'kite': 3,
        'swordfish': 4, 'reveal': 5}


def uref(u): return {'k': KIND[u], 'i': u % 9 + 1}
def cref(i): return [R(i) + 1, C(i) + 1]


def parse(g):
    """['.72.3..89', ...] or an 81-char string -> list of 81 ints."""
    s = ''.join(g) if not isinstance(g, str) else g
    return [0 if ch in '.0' else int(ch) for ch in s]


def candidates(board, elims=()):
    ex = {}
    for i, d in elims:
        ex.setdefault(i, set()).add(d)
    out = []
    for i in range(81):
        if board[i]:
            out.append(set())
        else:
            seen = {board[j] for j in PEERS[i]}
            out.append({d for d in range(1, 10) if d not in seen} - ex.get(i, set()))
    return out


def sees(a, b): return a != b and b in PEERS[a]


def mk(tech, **kw):
    s = {'tech': tech, 'tier': TIER[tech], 'place': None, 'elim': [], 'units': [], 'pattern': [],
         'sources': [], 'beams': [], 'blocked': [], 'links': [], 'marks': [], 'target': None, 'p': {}}
    s.update(kw)
    return s


# ------------------------------------------------------------------ tier 0/1
def find_mistakes(board, sol, givens):
    for i in range(81):
        if board[i] and board[i] != sol[i] and not givens[i]:
            clash = [j for j in PEERS[i] if board[j] == board[i]]
            yield mk('mistake', place=[i, sol[i]], target=i, sources=clash,
                     beams=[[j, i] for j in clash], units=list(UNITS_OF[i]),
                     p={'cell': cref(i), 'd': board[i], 'right': sol[i], 'clash': bool(clash)})


def full_houses(board):
    for u in UNITS:
        empty = [i for i in u if not board[i]]
        if len(empty) == 1:
            i = empty[0]
            d = (set(range(1, 10)) - {board[j] for j in u}).pop()
            yield mk('full_house', place=[i, d], target=i, units=[UNITS.index(u)],
                     p={'unit': uref(UNITS.index(u)), 'cell': cref(i), 'd': d})


def _block_source(board, j, d, u):
    """A placed d that stops cell j (outside unit u's own cells). Prefer straight-line sources."""
    best = None
    for k in PEERS[j]:
        if board[k] == d and k not in UNITS[u]:
            rank = 0 if (R(k) == R(j) or C(k) == C(j)) else 1
            if best is None or rank < best[0]:
                best = (rank, k)
    return best[1] if best else None


def hidden_singles(board, cands, kinds, pure_only):
    count = {d: sum(1 for x in board if x == d) for d in range(1, 10)}
    found = []
    for u in range(27):
        if KIND[u] not in kinds:
            continue
        cells = UNITS[u]
        have = {board[i] for i in cells}
        for d in range(1, 10):
            if d in have:
                continue
            spots = [i for i in cells if not board[i] and d in cands[i]]
            if len(spots) != 1:
                continue
            t = spots[0]
            blocked = []
            for j in cells:
                if j != t and not board[j]:
                    blocked.append([j, _block_source(board, j, d, u)])
            pure = all(s is not None for _, s in blocked)
            if pure_only and not pure:
                continue
            found.append((-count[d], u, d, t, blocked, pure))
    found.sort(key=lambda x: (x[0], x[1]))
    for _, u, d, t, blocked, pure in found:
        srcs = sorted({s for _, s in blocked if s is not None})
        beams = []
        for s in srcs:
            hit = [j for j, ss in blocked if ss == s]
            far = max(hit, key=lambda j: abs(R(j) - R(s)) + abs(C(j) - C(s)))
            beams.append([s, far])
        yield mk('hidden_single', place=[t, d], target=t, units=[u], sources=srcs, beams=beams,
                 blocked=blocked,
                 p={'unit': uref(u), 'cell': cref(t), 'd': d, 'kind': KIND[u],
                    'earlier': sum(1 for _, s in blocked if s is None)})


def naked_singles(board, cands, pure_only):
    for i in range(81):
        if board[i] or len(cands[i]) != 1:
            continue
        d = next(iter(cands[i]))
        srcs, seen, earlier = [], [], []
        for e in range(1, 10):
            if e == d:
                continue
            k = None
            for unit in UNITS_OF[i]:
                k = next((j for j in UNITS[unit] if board[j] == e), None)
                if k is not None:
                    break
            if k is None:
                earlier.append(e)
            else:
                srcs.append(k)
                seen.append(e)
        if pure_only and earlier:
            continue
        yield mk('naked_single', place=[i, d], target=i, units=list(UNITS_OF[i]), sources=srcs,
                 beams=[[k, i] for k in srcs],
                 p={'cell': cref(i), 'd': d, 'seen': seen, 'earlier': earlier})


# ------------------------------------------------------------------ tier 2/3 eliminations
def locked_candidates(board, cands):
    for b in range(9):                                   # pointing: box -> line
        box = 18 + b
        for d in range(1, 10):
            spots = [i for i in UNITS[box] if d in cands[i]]
            if len(spots) < 2:
                continue
            for kind, f, base in (('row', R, 0), ('col', C, 9)):
                if len({f(i) for i in spots}) == 1:
                    line = base + f(spots[0])
                    elim = [[j, d] for j in UNITS[line] if j not in UNITS[box] and d in cands[j]]
                    if elim:
                        yield mk('pointing', elim=elim, units=[box, line], pattern=spots,
                                 marks=[[i, d, 'keep'] for i in spots] + [[j, d, 'elim'] for j, _ in elim],
                                 p={'d': d, 'box': uref(box), 'line': uref(line), 'n': len(spots)})
    for line in range(18):                               # claiming: line -> box
        for d in range(1, 10):
            spots = [i for i in UNITS[line] if d in cands[i]]
            if len(spots) < 2 or len({B(i) for i in spots}) != 1:
                continue
            box = 18 + B(spots[0])
            elim = [[j, d] for j in UNITS[box] if j not in UNITS[line] and d in cands[j]]
            if elim:
                yield mk('claiming', elim=elim, units=[line, box], pattern=spots,
                         marks=[[i, d, 'keep'] for i in spots] + [[j, d, 'elim'] for j, _ in elim],
                         p={'d': d, 'box': uref(box), 'line': uref(line), 'n': len(spots)})


def naked_subsets(board, cands, n):
    tech = {2: 'naked_pair', 3: 'naked_triple'}[n]
    for u in (list(range(18, 27)) + list(range(18))):
        empty = [i for i in UNITS[u] if not board[i]]
        pool = [i for i in empty if 2 <= len(cands[i]) <= n]
        for combo in combinations(pool, n):
            digs = set().union(*(cands[i] for i in combo))
            if len(digs) != n:
                continue
            elim = [[j, d] for j in empty if j not in combo for d in sorted(digs & cands[j])]
            if elim:
                yield mk(tech, elim=elim, units=[u], pattern=list(combo),
                         marks=[[i, d, 'keep'] for i in combo for d in sorted(cands[i])]
                         + [[j, d, 'elim'] for j, d in elim],
                         p={'unit': uref(u), 'digits': sorted(digs), 'n': n})


def hidden_subsets(board, cands, n):
    tech = {2: 'hidden_pair', 3: 'hidden_triple'}[n]
    for u in (list(range(18, 27)) + list(range(18))):
        empty = [i for i in UNITS[u] if not board[i]]
        missing = [d for d in range(1, 10) if d not in {board[i] for i in UNITS[u]}]
        for digs in combinations(missing, n):
            where = {i for i in empty if cands[i] & set(digs)}
            if len(where) != n or any(not any(d in cands[i] for i in where) for d in digs):
                continue
            elim = [[i, d] for i in sorted(where) for d in sorted(cands[i] - set(digs))]
            if elim:
                yield mk(tech, elim=elim, units=[u], pattern=sorted(where),
                         marks=[[i, d, 'keep' if d in digs else 'elim'] for i in sorted(where)
                                for d in sorted(cands[i])],
                         p={'unit': uref(u), 'digits': list(digs), 'n': n})


def fish(board, cands, n):
    tech = {2: 'x_wing', 3: 'swordfish'}[n]
    for d in range(1, 10):
        for base_kind, f_base, f_cover, b0, c0 in (('row', R, C, 0, 9), ('col', C, R, 9, 0)):
            lines = []
            for k in range(9):
                spots = [i for i in UNITS[b0 + k] if d in cands[i]]
                if 2 <= len(spots) <= n:
                    lines.append((k, spots))
            for combo in combinations(lines, n):
                cover = sorted({f_cover(i) for _, sp in combo for i in sp})
                if len(cover) != n:
                    continue
                base = [k for k, _ in combo]
                cells = [i for _, sp in combo for i in sp]
                elim = [[j, d] for cv in cover for j in UNITS[c0 + cv]
                        if f_base(j) not in base and d in cands[j]]
                if elim:
                    links = [[sp[a], sp[a + 1], 'strong'] for _, sp in combo for a in range(len(sp) - 1)]
                    yield mk(tech, elim=elim, units=[b0 + k for k in base] + [c0 + c for c in cover],
                             pattern=cells, links=links,
                             marks=[[i, d, 'keep'] for i in cells] + [[j, d, 'elim'] for j, _ in elim],
                             p={'d': d, 'base': [uref(b0 + k) for k in base],
                                'cover': [uref(c0 + c) for c in cover], 'n': n})


def xy_wings(board, cands):
    bival = [i for i in range(81) if len(cands[i]) == 2]
    for p in bival:
        a, b = sorted(cands[p])
        wings = [q for q in bival if sees(p, q) and len(cands[q] & cands[p]) == 1]
        for q1, q2 in combinations(wings, 2):
            s1, s2 = cands[q1] - cands[p], cands[q2] - cands[p]
            if s1 != s2 or (cands[q1] & cands[p]) == (cands[q2] & cands[p]):
                continue
            z = next(iter(s1))
            elim = [[j, z] for j in range(81) if z in cands[j] and j not in (p, q1, q2)
                    and sees(j, q1) and sees(j, q2)]
            if elim:
                yield mk('xy_wing', elim=elim, pattern=[p, q1, q2],
                         links=[[p, q1, 'weak'], [p, q2, 'weak']],
                         marks=[[i, d, 'keep'] for i in (p, q1, q2) for d in sorted(cands[i])]
                         + [[j, z, 'elim'] for j, _ in elim],
                         p={'pivot': cref(p), 'w1': cref(q1), 'w2': cref(q2), 'z': z,
                            'ab': [a, b]})


def _two_spots(cands, d, unit):
    sp = [i for i in UNITS[unit] if d in cands[i]]
    return sp if len(sp) == 2 else None


def skyscrapers(board, cands):
    for d in range(1, 10):
        for b0, f_same in ((0, C), (9, R)):
            pairs = [(k, _two_spots(cands, d, b0 + k)) for k in range(9)]
            pairs = [(k, sp) for k, sp in pairs if sp]
            for (k1, s1), (k2, s2) in combinations(pairs, 2):
                for x1, y1 in (s1, s1[::-1]):
                    for x2, y2 in (s2, s2[::-1]):
                        if f_same(x1) != f_same(x2) or f_same(y1) == f_same(y2):
                            continue
                        elim = [[j, d] for j in range(81) if d in cands[j] and j not in (y1, y2)
                                and sees(j, y1) and sees(j, y2)]
                        if elim:
                            yield mk('skyscraper', elim=elim, units=[b0 + k1, b0 + k2], pattern=[x1, y1, x2, y2],
                                     links=[[x1, y1, 'strong'], [x2, y2, 'strong'], [x1, x2, 'weak']],
                                     marks=[[i, d, 'keep'] for i in (x1, y1, x2, y2)] + [[j, d, 'elim'] for j, _ in elim],
                                     p={'d': d, 'lines': [uref(b0 + k1), uref(b0 + k2)],
                                        'ends': [cref(y1), cref(y2)]})


def kites(board, cands):
    for d in range(1, 10):
        rows = [(r, _two_spots(cands, d, r)) for r in range(9)]
        cols = [(c, _two_spots(cands, d, 9 + c)) for c in range(9)]
        for r, rs in rows:
            if not rs:
                continue
            for c, cs in cols:
                if not cs or set(rs) & set(cs):
                    continue
                for xr, er in (rs, rs[::-1]):
                    for xc, ec in (cs, cs[::-1]):
                        if B(xr) != B(xc):
                            continue
                        elim = [[j, d] for j in range(81) if d in cands[j] and j not in (er, ec)
                                and sees(j, er) and sees(j, ec)]
                        if elim:
                            yield mk('kite', elim=elim, units=[r, 9 + c], pattern=[xr, er, xc, ec],
                                     links=[[xr, er, 'strong'], [xc, ec, 'strong'], [xr, xc, 'weak']],
                                     marks=[[i, d, 'keep'] for i in (xr, er, xc, ec)] + [[j, d, 'elim'] for j, _ in elim],
                                     p={'d': d, 'row': uref(r), 'col': uref(9 + c), 'box': uref(18 + B(xr)),
                                        'ends': [cref(er), cref(ec)]})


def reveal(board, cands, sol):
    empty = [i for i in range(81) if not board[i]]
    i = min(empty, key=lambda k: (len(cands[k]), k))
    return mk('reveal', place=[i, sol[i]], target=i, units=list(UNITS_OF[i]),
              marks=[[i, d, 'cand'] for d in sorted(cands[i])],
              p={'cell': cref(i), 'd': sol[i], 'options': sorted(cands[i])})


# ------------------------------------------------------------------ driver
def _ok(step, board, sol):
    if step['place'] and sol[step['place'][0]] != step['place'][1]:
        return False
    return all(sol[i] != d for i, d in step['elim'])


def generators(board, cands):
    yield full_houses(board)
    yield hidden_singles(board, cands, ('box',), True)
    yield hidden_singles(board, cands, ('row', 'col'), True)
    yield naked_singles(board, cands, True)
    yield hidden_singles(board, cands, ('box', 'row', 'col'), False)
    yield naked_singles(board, cands, False)
    yield locked_candidates(board, cands)
    yield naked_subsets(board, cands, 2)
    yield hidden_subsets(board, cands, 2)
    yield naked_subsets(board, cands, 3)
    yield hidden_subsets(board, cands, 3)
    yield fish(board, cands, 2)
    yield skyscrapers(board, cands)
    yield kites(board, cands)
    yield xy_wings(board, cands)
    yield fish(board, cands, 3)


REJECTED = []      # detector bugs caught by the solution check (tests read this)


def next_step(board, cands, sol, givens=None):
    """board: 81 ints, cands: 81 sets (already minus earlier eliminations), sol: 81 ints."""
    if givens is not None:
        for s in find_mistakes(board, sol, givens):
            return s
    for gen in generators(board, cands):
        for s in gen:
            if _ok(s, board, sol):
                return s
            REJECTED.append(s)
    if any(not x for x in board):
        return reveal(board, cands, sol)
    return None


def apply(step, board, elims):
    """Return (new_board, new_elims) after a step (used by tests and the coach)."""
    board = list(board)
    elims = set(elims)
    if step['place']:
        i, d = step['place']
        board[i] = d
    for i, d in step['elim']:
        elims.add((i, d))
    return board, elims


def solve_path(board, sol, limit=400):
    """Whole human solve path - for replay, tests and the game summary."""
    elims, path = set(), []
    for _ in range(limit):
        if all(board):
            break
        cands = candidates(board, elims)
        s = next_step(board, cands, sol)
        if s is None:
            break
        path.append(s)
        board, elims = apply(s, board, elims)
    return path
