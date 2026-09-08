# Project working agreements

## Commit and push policy

- Commit locally throughout the work without asking for routine commit confirmation. The user explicitly authorized frequent, granular local commits.
- Make each commit one coherent, reviewable change: a behavior, bug fix, refactor, test improvement, or documentation decision. Split larger plan tasks into smaller commits where meaningful.
- Keep a behavior change and the tests needed to verify it together when practical. Do not create arbitrary line-level commits merely to increase commit count.
- Run checks appropriate to the change before committing. Inspect the staged diff and run git diff --cached --check. Stage explicit paths or hunks; do not include unrelated user changes or secrets.
- Use concise English commit subjects with a conventional prefix such as feat:, fix:, test:, refactor:, docs:, or chore:. Describe the concrete change; use a body when motivation, tradeoffs, or validation help explain it.
- Preserve useful development history for the portfolio. Do not amend, squash, or rewrite existing history without user authorization.
- Never push without explicit user permission for that push. Permission to commit is not permission to push. Do not automatically sync or publish changes.
- Report meaningful completed changes and local commits concisely. Do not claim tests or platform checks passed unless they were actually run.

## Development environment

- Support development and execution on both Windows and macOS.
- Follow the approved design and implementation plan under docs/superpowers/.
