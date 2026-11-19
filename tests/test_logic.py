"""The step solver: every step is a real human technique and never teaches a wrong move."""
from collections import Counter
import pytest

import logic as L
from tools.puzzles import bt, gen

FIXED = {
    'user_dryrun': '6.2......' '3....2.5.' '84.3...7.' '.8.4...9.' '.2.......' '.3..1..65' '...2..5.6' '.68..49.1' '.5.9....8',
    'game9': '.72.3..89' '5..8.....' '8...4....' '...9.287.' '..3..5.2.' '.........' '3...1.5..' '..7......' '......691',
    'xwing_wiki': '1.....569492.561.8.561.924...964.8.1.64.1....218.356.4.4.5...169.5.614.2621.....5',
    'inkala': '8..........36......7..9.2...5...7.......457.....1...3...1....68..85...1..9....4..',
}


def puzzles():
    out = []
    for name, s in FIXED.items():
        b = L.parse(s)
        sols = bt(b, 2)
        if len(sols) == 1:
            out.append(pytest.param(b, sols[0], id=name))
    for seed in range(8):
        b, f = gen(seed)
        out.append(pytest.param(b, f, id=f'gen{seed}'))
    return out


def test_parse_reads_dots_and_zeros():
    b = L.parse('1.3' + '0' * 78)
    assert len(b) == 81 and b[:3] == [1, 0, 3] and not any(b[3:])


def test_candidates_on_empty_board():
    cands = L.candidates([0] * 81)
    assert all(c == set(range(1, 10)) for c in cands)


def test_candidates_respect_peers():
    b = [0] * 81
    b[0] = 5
    cands = L.candidates(b)
    assert 5 not in cands[1] and 5 not in cands[9] and 5 not in cands[10]
    assert 5 in cands[40]


@pytest.mark.parametrize('board,sol', puzzles())
def test_solve_path_reaches_solution(board, sol):
    L.REJECTED.clear()
    path = L.solve_path(board, sol)
    b, el = list(board), set()
    for s in path:
        assert s['tech'] in L.TECHS
        if s['place']:
            i, d = s['place']
            assert sol[i] == d, f"{s['tech']} placed a wrong digit"
        for i, d in s['elim']:
            assert sol[i] != d, f"{s['tech']} removed the right digit"
        b, el = L.apply(s, b, el)
    assert b == sol
    assert not L.REJECTED, Counter(s['tech'] for s in L.REJECTED)


def test_wrong_entry_is_reported_first():
    b, sol = gen(3)
    givens = [bool(x) for x in b]
    i = next(k for k in range(81) if not b[k])
    b[i] = sol[i] % 9 + 1
    s = L.next_step(b, L.candidates(b), sol, givens)
    assert s['tech'] == 'mistake'
    assert s['place'] == [i, sol[i]]


def test_hard_puzzles_use_advanced_techniques():
    used = Counter()
    for name in ('xwing_wiki', 'inkala'):
        b = L.parse(FIXED[name])
        used.update(s['tech'] for s in L.solve_path(b, bt(b, 1)[0]))
    assert set(used) - {'full_house', 'hidden_single', 'naked_single'}
