#!/bin/zsh
# Double-click to open Sudoku Studio (Play, Learn, Help).
cd "$(dirname "$0")"
exec .venv/bin/python sudoku_app.py "$@"
