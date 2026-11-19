"""Pure parts of the autoplayer that run without a Mac: solver and tap map."""
import sudoku_auto as SA

PUZZLE = ['.72.3..89', '5..8.....', '8...4....', '...9.287.', '..3..5.2.',
          '.........', '3...1.5..', '..7......', '......691']


def test_solver_finds_the_unique_solution():
    count, sol = SA.solve(PUZZLE)
    assert count == 1 and sol is not None
    rows = [list(r) for r in sol]
    for r in range(9):
        for c in range(9):
            if PUZZLE[r][c] != '.':
                assert rows[r][c] == PUZZLE[r][c]
    digits = set('123456789')
    assert all(set(r) == digits for r in rows)
    assert all({rows[r][c] for r in range(9)} == digits for c in range(9))
    assert all({rows[b // 3 * 3 + i][b % 3 * 3 + j] for i in range(3) for j in range(3)} == digits
               for b in range(9))


def test_valid_rejects_duplicates():
    assert SA.valid(PUZZLE)
    bad = list(PUZZLE)
    bad[0] = '772.3..89'
    assert not SA.valid(bad)


def test_two_solutions_are_detected():
    count, _ = SA.solve(['.' * 9] * 9)
    assert count == 2


def test_number_pad_positions():
    assert [SA.padx(d) for d in (1, 5, 9)] == [33, 169, 305]
    assert len(SA.XS) == len(SA.YS) == 9
