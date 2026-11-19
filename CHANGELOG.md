# Changelog

All notable changes to this project are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-11-19

### Added
- Sudoku Studio: one book-shaped window with three chapters, Play, Learn and Help
- Autoplayer (`sudoku_auto.py`): screen recognition, digit templates, unique-solution check,
  five fill orders, three tap speeds, pop-up handling, resume and repair of a started puzzle, dry run
- Coach (`coach.py`): four-stage lessons with manual Next, optional auto-advance, *Me* mode with
  answer check and *Show answer*, review of earlier steps, progress per technique
- Step solver (`logic.py`) with 15 techniques, each step verified against the full solution
- Click-through overlay that draws each step over the mirrored phone
- Help chapter: ready check with fix buttons, technique library on real boards, keys, troubleshooting
- English and Arabic with right-to-left layout and optional Arabic-Indic digits
- Test suite that runs without a Mac, and a GitHub Actions workflow
- README in Arabic (default, `README.md`) and English (`README.en.md`), with a real iPhone Mirroring screenshot

[Unreleased]: https://github.com/alivx/sudoku-studio/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/alivx/sudoku-studio/releases/tag/v0.1.0
