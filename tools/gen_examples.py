#!/usr/bin/env python3
"""Rebuild web/examples.js: one real board for every technique the coach teaches.

Run from the repo root:  python tools/gen_examples.py
"""
import json, os, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import logic as L
from tools.puzzles import bt, gen

KNOWN = {
    'g9': '.72.3..89' '5..8.....' '8...4....' '...9.287.' '..3..5.2.' '.........' '3...1.5..' '..7......' '......691',
    'xw': '1.....569492.561.8.561.924...964.8.1.64.1....218.356.4.4.5...169.5.614.2621.....5',
    'ink': '8..........36......7..9.2...5...7.......457.....1...3...1....68..85...1..9....4..',
    'sf': '16.543.7..786.14354358.76.172.458.696..912.57...376..4.16.3..4.3...8..16..71645.3',
    'ht': '.....1.3.231.9.....65..31..6789243..1.3.5...6...1367....936.57...6.198433........',
}


def scan(name, b, sol, ex):
    bb, el = list(b), set()
    for _ in range(300):
        if all(bb):
            break
        c = L.candidates(bb, el)
        s = L.next_step(bb, c, sol)
        if s is None:
            break
        if s['tech'] not in ex:
            ex[s['tech']] = {'board': list(bb), 'cands': [sorted(x) for x in c], 'step': s, 'src': name}
        bb, el = L.apply(s, bb, el)


def main(budget=200):
    want, ex = set(L.TECHS) - {'mistake'}, {}
    for k, s in KNOWN.items():
        b = L.parse(s)
        sols = bt(b, 2)
        if len(sols) == 1:
            scan(k, b, sols[0], ex)
    t0, seed = time.time(), 1000
    while time.time() - t0 < budget and not want <= set(ex):
        b, f = gen(seed)
        scan(f'gen{seed}', b, f, ex)
        seed += 1
    print('found', sorted(ex), 'missing', sorted(want - set(ex)))
    out = os.path.join(ROOT, 'web', 'examples.js')
    with open(out, 'w') as f:
        f.write('window.EXAMPLES = ' + json.dumps(ex, separators=(',', ':')) + ';\n')
    print('wrote', out)


if __name__ == '__main__':
    main()
