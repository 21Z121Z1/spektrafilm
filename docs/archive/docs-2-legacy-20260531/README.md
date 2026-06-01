# Legacy `docs 2` Snapshot

This directory contains the tracked files that previously lived at the top-level `docs 2/` path.

The old path was problematic because it duplicated `docs/dev/`, included spaces in the documentation root, and made it unclear which copy was canonical. The files were moved here instead of deleted so older implementation notes and review evidence remain available.

## How To Use This Archive

- Start with [`../../README.md`](../../README.md) for current documentation routing.
- Use [`dev/`](dev/) only when a current plan or report explicitly needs the old snapshot.
- When a file exists both here and in `../../dev/`, prefer the current `../../dev/` copy unless you are comparing historical differences.
- Do not apply recommendations from this archive mechanically. Re-check current source, tests, and newer reports first.
