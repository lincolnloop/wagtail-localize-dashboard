# Changelog

## Unreleased

### Added

- Translation rows now show how much of a translation is actually live, not
  just how much has been translated. Where the two differ, the row is marked
  with an inset ring, an upload icon and a `(N% live)` badge.
- `TranslationProgress.to_dict()` and `SnippetTranslationProgress.to_dict()`
  gain two keys, `percent_published` (`int | None`) and
  `has_unpublished_translations` (`bool`). The latter is now a stored
  `BooleanField`, computed from raw segment counts
  (`published_segments < translated_segments`) when progress is rebuilt,
  rather than derived from the two displayed percentages.

### Fixed

- Progress was silently never rebuilt for objects whose rich text contained the
  same phrase twice: the `StringTranslation` signal handlers raised
  `MultipleObjectsReturned` into a bare `except`.
- `has_unpublished_translations` was derived by comparing two `int()`-truncated
  percentages, which collide on sources with more than 100 segments and hid a
  real publish gap whenever that truncation made both percentages equal.
- The amber status color (`#faa500`) failed WCAG AA against white text at
  2.01:1 and is now `#a06400` at 4.86:1.

### Upgrading

Existing progress rows have no published percentage until they are recomputed,
and render exactly as before until then. Rows refresh automatically when a page
or snippet is edited. To populate them all at once:

    python manage.py rebuild_translation_progress
