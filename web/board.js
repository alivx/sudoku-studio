// board.js - draws the coach's explanations on a Sudoku board (used by the phone overlay and by Help).
// Coordinates are the iPhone Mirroring reference frame (339 x 747); the grid sits at (12,170)-(327,488).
(function () {
  if (!document.getElementById('sb-style')) {
    const st = document.createElement('style'); st.id = 'sb-style';
    st.textContent = `.sb-fade{animation:sbfade .45s ease-out both}
.sb-pop{animation:sbpop .5s cubic-bezier(.2,1.4,.4,1) both;transform-box:fill-box;transform-origin:center}
.sb-draw{stroke-dasharray:400;stroke-dashoffset:400;animation:sbdraw .7s ease-out forwards}
.sb-pulse{animation:sbpulse 1.4s ease-in-out infinite}
@keyframes sbfade{from{opacity:0}to{opacity:1}}
@keyframes sbpop{0%{opacity:0;transform:scale(.3)}100%{opacity:1;transform:scale(1)}}
@keyframes sbdraw{to{stroke-dashoffset:0}}
@keyframes sbpulse{0%,100%{opacity:1}50%{opacity:.45}}
@media (prefers-reduced-motion: reduce){.sb-fade,.sb-pop,.sb-draw,.sb-pulse{animation:none;stroke-dashoffset:0;opacity:1}}`;
    document.head.appendChild(st);
  }
  let counter = 0;
  window.makeBoard = function (svg) {
    const MID = 'sbm' + (++counter);
    const G = {x0: 12, y0: 170, x1: 327, y1: 488};
    const CW = (G.x1 - G.x0) / 9, CH = (G.y1 - G.y0) / 9;
    const COL = {purple: '#534AB7', purpleL: '#7F77DD', purpleBg: 'rgba(127,119,221,.22)',
                 coral: '#D85A30', coralBg: 'rgba(216,90,48,.22)', red: '#E24B4A', gray: '#888780'};
    const NS = 'http://www.w3.org/2000/svg';
    const R = i => Math.floor(i / 9), C = i => i % 9;
    const cx = i => G.x0 + C(i) * CW + CW / 2, cy = i => G.y0 + R(i) * CH + CH / 2;
    const UNIT = u => u < 9 ? [...Array(9)].map((_, c) => u * 9 + c)
      : u < 18 ? [...Array(9)].map((_, r) => r * 9 + (u - 9))
      : [...Array(9)].map((_, k) => (Math.floor((u - 18) / 3) * 3 + Math.floor(k / 3)) * 9 + (u - 18) % 3 * 3 + k % 3);

    function el(tag, attrs, parent, cls, delay) {
      const e = document.createElementNS(NS, tag);
      for (const k in attrs) e.setAttribute(k, attrs[k]);
      if (cls) e.setAttribute('class', cls);
      if (delay) e.style.animationDelay = delay + 's';
      (parent || svg).appendChild(e); return e;
    }
    function cellBox(i, pad) { pad = pad || 0; return {x: G.x0 + C(i) * CW + pad, y: G.y0 + R(i) * CH + pad, width: CW - 2 * pad, height: CH - 2 * pad}; }
    function mini(i, d) {
      const k = d - 1, x = G.x0 + C(i) * CW + 7 + (k % 3) * (CW - 14) / 2, y = G.y0 + R(i) * CH + 8 + Math.floor(k / 3) * (CH - 15) / 2;
      return [x, y];
    }

    function demoBoard(board) {
      const g = el('g', {});
      el('rect', {x: G.x0, y: G.y0, width: G.x1 - G.x0, height: G.y1 - G.y0, fill: '#fff'}, g);
      for (let k = 0; k <= 9; k++) {
        const w = k % 3 ? .6 : 2;
        el('line', {x1: G.x0 + k * CW, y1: G.y0, x2: G.x0 + k * CW, y2: G.y1, stroke: '#333', 'stroke-width': w}, g);
        el('line', {x1: G.x0, y1: G.y0 + k * CH, x2: G.x1, y2: G.y0 + k * CH, stroke: '#333', 'stroke-width': w}, g);
      }
      board.forEach((d, i) => { if (d) { const t = el('text', {x: cx(i), y: cy(i) + 7, 'text-anchor': 'middle', 'font-size': 20, fill: '#222', 'font-family': 'Helvetica'}, g); t.textContent = d; } });
    }
    let data_lang = 'en';
    function render(data) {
      svg.innerHTML = '';
      data_lang = (data && data.lang) || 'en';
      if (data && data.demo && data.board) demoBoard(data.board);
      if (data && data.correct != null && !data.step) { drawCorrect(data.correct); return; }
      if (!data || !data.step) { if (data) { drawMemory(data, new Set()); if (data.showCands) drawCands(data, new Set()); } return; }
      const st = data.step, stage = data.stage, focus = new Set();
      if (window.T) T.set(data.lang || 'en', data.eastern);
      st.units.forEach(u => UNIT(u).forEach(i => focus.add(i)));
      const single = ['naked_single', 'mistake', 'reveal'].includes(st.tech);
      if (st.target != null && (single || stage >= 3)) focus.add(st.target);
      if (stage >= 1) {                          // stage 0 only says where to look; the clues come with "What"
        st.pattern.forEach(i => focus.add(i));
        (st.sources || []).forEach(i => focus.add(i));
      }
      if (stage >= 2) st.elim.forEach(([i]) => focus.add(i));

      // 1. spotlight: dim the board outside the focus
      const defs = el('defs', {});
      const mask = el('mask', {id: MID}, defs);
      el('rect', {x: 0, y: 0, width: 339, height: 747, fill: 'white'}, mask);
      focus.forEach(i => el('rect', Object.assign(cellBox(i), {fill: 'black'}), mask));
      el('rect', {x: G.x0, y: G.y0, width: G.x1 - G.x0, height: G.y1 - G.y0, fill: 'rgba(20,18,40,.42)', mask: 'url(#' + MID + ')'}, svg, 'sb-fade');
      st.units.forEach(u => {
        const cs = UNIT(u), a = cs[0], b = cs[8];
        el('rect', {x: G.x0 + C(a) * CW + 1, y: G.y0 + R(a) * CH + 1, width: (C(b) - C(a) + 1) * CW - 2, height: (R(b) - R(a) + 1) * CH - 2,
          fill: 'none', stroke: COL.purpleL, 'stroke-width': 1.6, 'stroke-dasharray': '4 3', rx: 3}, svg, 'sb-fade');
      });
      if (window.T && stage <= 1) st.units.slice(0, 2).forEach((u, k) => unitLabel(u, k));
      drawMemory(data, focus);
      if (stage < 1) { if (data.showCands) drawCands(data, focus); return; }

      // 2. what: the cells and digits doing the work
      (st.sources || []).forEach((i, k) => el('circle', {cx: cx(i), cy: cy(i), r: 14, fill: COL.coralBg, stroke: COL.coral, 'stroke-width': 2}, svg, 'sb-pop', k * .06));
      st.pattern.forEach((i, k) => el('rect', Object.assign(cellBox(i, 2), {fill: COL.purpleBg, stroke: COL.purple, 'stroke-width': 2.2, rx: 5}), svg, 'sb-pop', k * .08));
      if (st.tech === 'naked_single' || st.tech === 'mistake' || st.tech === 'reveal')
        el('rect', Object.assign(cellBox(st.target, 2), {fill: 'none', stroke: COL.purple, 'stroke-width': 2.5, rx: 5}), svg, 'sb-pulse');

      // 3. why: beams, blocked cells, links, candidate marks
      if (stage >= 2) {
        (st.beams || []).forEach(([a, b], k) => el('line', {x1: cx(a), y1: cy(a), x2: cx(b), y2: cy(b), stroke: COL.coral,
          'stroke-width': 4, 'stroke-linecap': 'round', opacity: .55}, svg, 'sb-draw', k * .12));
        (st.blocked || []).forEach(([i, s], k) => {
          const col = s == null ? COL.gray : COL.coral;
          const g = el('g', {}, svg, 'sb-fade', .35 + k * .07);
          el('line', {x1: cx(i) - 7, y1: cy(i) - 7, x2: cx(i) + 7, y2: cy(i) + 7, stroke: col, 'stroke-width': 2.4, 'stroke-linecap': 'round'}, g);
          el('line', {x1: cx(i) + 7, y1: cy(i) - 7, x2: cx(i) - 7, y2: cy(i) + 7, stroke: col, 'stroke-width': 2.4, 'stroke-linecap': 'round'}, g);
        });
        (st.links || []).forEach(([a, b, kind], k) => el('line', {x1: cx(a), y1: cy(a), x2: cx(b), y2: cy(b), stroke: COL.purple,
          'stroke-width': 2, 'stroke-dasharray': kind === 'weak' ? '5 4' : 'none', opacity: .55}, svg, 'sb-fade', .2 + k * .1));
      }
      if (stage >= 2) {
        const ec = [...new Set(st.elim.map(([i]) => i))];
        ec.forEach((i, k) => el('rect', Object.assign(cellBox(i, 2), {fill: 'rgba(226,75,74,.13)', stroke: COL.red, 'stroke-width': 1.4, rx: 5}), svg, 'sb-fade', .3 + k * .05));
      }
      const marked = new Set();
      (st.marks || []).forEach(([i, d, kind], k) => {
        marked.add(i);
        if (stage < 2 && kind === 'elim') kind = 'cand';
        const [x, y] = mini(i, d);
        const color = kind === 'keep' ? COL.purple : kind === 'elim' ? COL.red : COL.gray;
        if (kind === 'keep') el('circle', {cx: x, cy: y - .5, r: 6.2, fill: COL.purpleBg}, svg, 'sb-fade');
        if (kind === 'elim') el('circle', {cx: x, cy: y - .5, r: 6.2, fill: 'rgba(255,255,255,.85)'}, svg, 'sb-fade');
        const t = el('text', {x, y: y + 3.6, 'text-anchor': 'middle', 'font-size': 10.5, 'font-weight': 700, fill: color,
          'font-family': '-apple-system, Helvetica'}, svg, 'sb-fade', k * .02);
        t.textContent = d;
        if (kind === 'elim') el('line', {x1: x - 6, y1: y + 5, x2: x + 6, y2: y - 5, stroke: COL.red, 'stroke-width': 2}, svg, 'sb-draw', .5 + k * .05);
      });
      if (data.showCands) drawCands(data, marked);

      // 4. answer: ghost digit
      if (stage >= 3 && st.place) {
        const [i, d] = st.place;
        el('rect', Object.assign(cellBox(i, 1.5), {fill: 'rgba(238,237,254,.92)', stroke: COL.purple, 'stroke-width': 2.5, rx: 5}), svg, 'sb-pop');
        const t = el('text', {x: cx(i), y: cy(i) + 8, 'text-anchor': 'middle', 'font-size': 23, 'font-weight': 600, fill: COL.purple,
          'font-family': '-apple-system, Helvetica'}, svg, 'sb-pop', .1);
        t.textContent = d;
      }
    }

    function unitLabel(u, k) {
      const cs = UNIT(u), a = cs[0];
      let name = T.unit({k: u < 9 ? 'row' : u < 18 ? 'col' : 'box', i: u % 9 + 1});
      if (data_lang === 'en') name = name[0].toUpperCase() + name.slice(1);
      const x = G.x0 + C(a) * CW + 2 + k * 4, y = G.y0 + R(a) * CH - 13 - k * 13;
      const w = name.length * 5.4 + 8;
      const g = el('g', {}, svg, 'sb-fade', .1);
      el('rect', {x, y, width: w, height: 11.5, rx: 3, fill: COL.purple}, g);
      const t = el('text', {x: x + w / 2, y: y + 8.6, 'text-anchor': 'middle', 'font-size': 8.5, 'font-weight': 600, fill: '#fff',
        'font-family': '-apple-system, "SF Arabic", Helvetica', direction: (data_lang === 'ar' ? 'rtl' : 'ltr')}, g);
      t.textContent = name;
    }
    function drawMemory(data, skip) {
      // options the coach already removed in earlier steps: the phone can't show them, so keep them visible here
      (data.memory || []).forEach(([i, left]) => {
        if (skip.has(i) || (data.board && data.board[i])) return;
        left.forEach(d => {
          const [x, y] = mini(i, d);
          const t = el('text', {x, y: y + 3, 'text-anchor': 'middle', 'font-size': 8, fill: COL.gray, opacity: .9, 'font-family': '-apple-system, Helvetica'});
          t.textContent = d;
        });
      });
    }
    function drawCorrect(i) {
      el('rect', Object.assign(cellBox(i, 1.5), {fill: 'rgba(151,196,89,.25)', stroke: '#3B6D11', 'stroke-width': 2.5, rx: 5}), svg, 'sb-pop');
    }
    function drawCands(data, skip) {
      if (!data.cands || !data.board) return;
      data.cands.forEach((cs, i) => {
        if (data.board[i] || skip.has(i)) return;
        cs.forEach(d => {
          const [x, y] = mini(i, d);
          const t = el('text', {x, y: y + 3, 'text-anchor': 'middle', 'font-size': 8, fill: COL.gray, 'font-family': '-apple-system, Helvetica'});
          t.textContent = d;
        });
      });
    }

    return {render};
  };
})();
