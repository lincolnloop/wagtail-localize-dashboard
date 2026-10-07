# Changelog

## Unreleased

### Added

- Translation rows now show how much of a translation is actually live, not
  just how much has been translated. Where the two differ, the row is marked
  with an inset ring, an upload icon and a `(N% live)` badge.
- `TranslationProgress.to_dict()` and `SnippetTranslationProgress.to_dict()`
  gain two keys, `percent_published` (`int | None`) and
  `has_unpublished_translations` (`bool`).
- `get_translation_progress`, which returns a tuple of `percent_translated`,
  `percent_published`, and `has_unpublished_translations`.
- `WAGTAIL_LOCALIZE_DASHBOARD_PRESERVE_TIMESTAMP_ON_NOOP_SAVES` (default
  `True`) preserves `StringTranslation.updated_at` at its stored value when a
  save alters neither the text nor the error state. This behavior exists to
  avoid lowering the translated percentage when a user updates a segment without
  making any changes to the segment.

### Fixed

- Re-saving a translated segment without changing its text no longer lowers a
  fully published page's published percenage.
- Progress was silently never rebuilt for objects whose rich text contained the
  same phrase twice: the `StringTranslation` signal handlers raised
  `MultipleObjectsReturned` into a bare `except`.
- The amber status color (`#faa500`) failed WCAG AA against white text at
  2.01:1 and is now `#a06400` at 4.86:1.

### Deprecated

- `get_translation_percentages` deprecated in favor of 
  `get_translation_progress`.

### Upgrading

Existing progress rows have no published percentage until they are recomputed,
and render exactly as before until then. Rows refresh automatically when a page
or snippet is edited. To populate them all at once:

    python manage.py rebuild_translation_progress
