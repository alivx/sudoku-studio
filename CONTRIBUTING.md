# Contributing

Thanks for helping. Bug reports, translations, new techniques and calibration for other games are
all welcome.

## Set up

```bash
git clone https://github.com/alivx/sudoku-studio.git
cd sudoku-studio
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

The tests run on macOS and Linux and need no phone. To try the UI without a phone, run
`.venv/bin/python sudoku_app.py --demo`.

## Before you open a pull request

- Keep it rule-based: no AI models, no network calls.
- Run `python -m pytest` and make sure it passes. Add a test for a bug fix or a new feature.
- New technique in `logic.py`: add it to `TECHS` and `TIER`, add its text to both languages in
  `web/i18n.js`, then run `python tools/gen_examples.py` so the Help library gets a real example.
- UI text goes in `web/i18n.js` in both English and Arabic. If you can't write one of them, say so
  in the pull request and someone will help.
- Check the UI in Arabic too: right-to-left layout is easy to break.
- The README comes in two files: `README.md` (Arabic, default) and `README.en.md` (English).
  Change both, or say in the pull request which one still needs updating.
- Don't commit logs, `debug/` screenshots or settings files.

## Reporting a bug

Use the bug report template. Run with `--dry-run` if you can, and attach the relevant lines of
`sudoku_auto.log` or `coach.log`. Look at screenshots from `debug/` before attaching them: they show
whatever was in the mirroring window.

## Style

- Python 3.10+, standard library plus `numpy`, `pillow` and PyObjC.
- Small functions with a short docstring that says what they return.
- UI copy: sentence case, verb plus noun on buttons ("Start learning"), no "OK".
