# Changelog

## Unreleased

### Removed

- Support for Django 4.2-5.1 and Wagtail 5.2-6.x. Those versions are not
  supported by the current `wagtail-localize`, so we don't (explicitly) support
  them here.
- The unused `docs` extra (mkdocs, mkdocs-material, mkdocstrings), and the
  unused `black`, `flake8`, `isort` and `mypy` entries in the `dev` extra.

### Added

- Translation rows now show how much of a translation is actually live, not
  just how much has been translated. Where the two differ, the row is marked
  with an inset ring, an upload icon and a `(N% live)` badge.
- `TranslationProgress.to_dict()` and `SnippetTranslationProgress.to_dict()`
  gain two keys, `percent_published` (`int | None`) and
  `has_unpublished_translations` (`bool`).
- `get_translation_progress`, which returns a tuple of `percent_translated`,
  `percent_published`, and `has_unpublished_translations`.
- A segment re-saved without changes counts as unpublished until the next
  push: upstream records no per-segment push provenance, so an identical
  re-save still bumps `updated_at` and drops the segment from the published
  count.
- A supported matrix is now declared in `pyproject.toml` as hatch
  environments and tested in CI: Django 5.2/6.0/6.1 against Wagtail
  7.0/7.4/8.0 on Python 3.10 through 3.14.
- `dev` now installs the `test` extra plus a pinned `ruff`.
- We now define `ruff` (lint) rules specifically, and upgrade `ruff` version.

### Fixed

- Progress was silently never rebuilt for objects whose rich text contained the
  same phrase twice: the `StringTranslation` signal handlers raised
  `MultipleObjectsReturned` into a bare `except`.
- The amber status color (`#faa500`) failed WCAG AA against white text at
  2.01:1 and is now `#a06400` at 4.86:1.
- A few color contrast issues (white text on amber in the 80-99% translation
  badge, grey text in the "No translations" message)

### Deprecated

- `get_translation_percentages` deprecated in favor of 
  `get_translation_progress`.

### Upgrading

Existing progress rows have no published percentage until they are recomputed,
and render exactly as before until then. Rows refresh automatically when a page
or snippet is edited. To populate them all at once:

    python manage.py rebuild_translation_progress
