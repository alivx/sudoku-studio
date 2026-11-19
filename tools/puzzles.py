"""Small puzzle helpers shared by the tests and tools: a backtracking solver and a generator."""
import random

ROWS = [[r * 9 + c for c in range(9)] for r in range(9)]
COLS = [[r * 9 + c for r in range(9)] for c in range(9)]
BOXES = [[(b // 3 * 3 + i) * 9 + b % 3 * 3 + j for i in range(3) for j in range(3)] for b in range(9)]
PEERS = [set() for _ in range(81)]
for unit in ROWS + COLS + BOXES:
    for i in unit:
        PEERS[i].update(j for j in unit if j != i)


def bt(board, limit=2, rnd=None):
    """Return up to `limit` solutions of an 81-int board (0 = empty)."""
    cells, sols = list(board), []

    def cand(i):
        return [d for d in range(1, 10) if all(cells[j] != d for j in PEERS[i])]

    def rec():
        best = None
        for i in range(81):
            if not cells[i]:
                cs = cand(i)
                if best is None or len(cs) < len(best[1]):
                    best = (i, cs)
                if len(cs) <= 1:
                    break
        if best is None:
            sols.append(list(cells))
            return len(sols) >= limit
        i, cs = best
        if rnd:
            rnd.shuffle(cs)
        for d in cs:
            cells[i] = d
            if rec():
                return True
        cells[i] = 0
        return False

    rec()
    return sols


def gen(seed):
    """Make a puzzle with a unique solution. Returns (puzzle, solution)."""
    rnd = random.Random(seed)
    full = bt([0] * 81, 1, rnd)[0]
    p = list(full)
    order = list(range(81))
    rnd.shuffle(order)
    for i in order:
        v, p[i] = p[i], 0
        if len(bt(p, 2)) != 1:
            p[i] = v
    return p, full
