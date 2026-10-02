# Changelog

## 0.6.0

### Added

- Pre-commit hooks for linting, and a `pre-commit` CI workflow.

### Removed

- Support for Django 4.2-5.1 and Wagtail 5.2-6.x. Those versions are not
  supported by the current `wagtail-localize`, so we don't (explcitily) support
  them here.
- The unused `docs` extra (mkdocs, mkdocs-material, mkdocstrings), and the
  unused `black`, `flake8`, `isort` and `mypy` entries in the `dev` extra.

### Fixed

- a few color contrast issues (white text on amber in the 80-99% translation
  badge, grey text in the "No translations" message)

### Changed

- A supported matrix is now declared in `pyproject.toml` as hatch
  environments and tested in CI: Django 5.2/6.0/6.1 against Wagtail
  7.0/7.4/8.0 on Python 3.10 through 3.14.
- `dev` now installs the `test` extra plus a pinned `ruff`.
- We now define `ruff` (lint) rules specifically, and upgrade `ruff` version.
