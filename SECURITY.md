# Security policy

## Supported versions

Only the latest release on the `main` branch gets fixes.

## Reporting a vulnerability

Please report security problems privately through
[GitHub private vulnerability reporting](https://github.com/alivx/sudoku-studio/security/advisories/new)
rather than in a public issue. Include what you found, how to reproduce it and what it could affect.
You should get a reply within a week.

## What this project can access

Sudoku Studio needs macOS **Accessibility** (to send taps) and **Screen Recording** (to take
screenshots of the iPhone Mirroring window). It runs locally, makes no network requests and sends
no data anywhere. Logs and debug screenshots are written to the project folder only.

Grant these permissions only to the Terminal or Python you use for this project, and remove them
when you no longer need them.
