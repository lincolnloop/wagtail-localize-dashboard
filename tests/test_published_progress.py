"""Tests for the published-translation percentage."""

from unittest.mock import patch

import pytest
from django.db import transaction
from django.test import override_settings
from wagtail_localize.models import (
    StringSegment,
    StringTranslation,
    Translation,
    TranslationLog,
    TranslationSource,
)

from tests.models import DraftStateSnippet, RichTextSnippet, SampleSnippet
from wagtail_localize_dashboard.models import (
    SnippetTranslationProgress,
    TranslationProgress,
)
from wagtail_localize_dashboard.utils import (
    create_page_translation_progress,
    create_snippet_translation_progress,
    get_translation_progress,
)

pytestmark = [pytest.mark.django_db]

# Ensure save_target() actually publishes, since wagtail-localize defers
# publishing to transaction.on_commit().
run_on_commit = patch.object(transaction, "on_commit", side_effect=lambda func: func())


def translate_segment(source, locale, path, text, has_error=False):
    """Translate one field of a source into a locale."""
    segment = (
        StringSegment.objects.filter(source=source, context__path=path)
        .order_by("order")
        .first()
    )
    StringTranslation.objects.update_or_create(
        translation_of=segment.string,
        context=segment.context,
        locale=locale,
        defaults={"data": text, "has_error": has_error},
    )


def segment_paths(source):
    return list(
        StringSegment.objects.filter(source=source)
        .order_by("order")
        .values_list("context__path", flat=True)
    )


def target_of(source_object, locale):
    return type(source_object).objects.get(
        translation_key=source_object.translation_key, locale=locale
    )


@pytest.fixture
def page_translation(test_page, locale_de):
    """A page with a German Translation record, nothing pushed yet."""
    source, __ = TranslationSource.get_or_create_from_instance(test_page)
    translation, __ = Translation.objects.get_or_create(
        source=source, target_locale=locale_de
    )
    return test_page, source, translation


@run_on_commit
def test_everything_translated_and_pushed_reports_equal_percentages(
    _on_commit, page_translation, locale_de
):
    page, source, translation = page_translation
    for path in segment_paths(source):
        translate_segment(source, locale_de, path, f"DE {path}")
    translation.save_target(publish=True)

    target = target_of(page, locale_de)
    assert target.live is True, "the on_commit patch must have published the target"

    percent_translated, percent_published = get_translation_progress(
        page, locale_de, target
    )
    total, translated = translation.get_progress()
    assert percent_translated == int(translated / total * 100)
    assert percent_published == percent_translated


@run_on_commit
def test_translation_saved_after_the_last_push_is_not_counted(
    _on_commit, page_translation, locale_de
):
    page, source, translation = page_translation
    paths = segment_paths(source)
    assert len(paths) >= 2, "fixture needs at least two translatable segments"

    translate_segment(source, locale_de, paths[0], "DE first")
    translation.save_target(publish=True)
    translate_segment(source, locale_de, paths[1], "DE second")

    target = target_of(page, locale_de)
    percent_translated, percent_published = get_translation_progress(
        page, locale_de, target
    )
    total, translated = translation.get_progress()
    assert percent_translated == int(translated / total * 100)
    assert percent_published == int(1 / total * 100)
    assert percent_published < percent_translated


@run_on_commit
def test_retranslating_one_field_counts_once(_on_commit, page_translation, locale_de):
    page, source, translation = page_translation
    path = segment_paths(source)[0]
    for i in range(4):
        translate_segment(source, locale_de, path, f"DE version {i}")
    translation.save_target(publish=True)

    total, __ = translation.get_progress()
    __, percent_published = get_translation_progress(
        page, locale_de, target_of(page, locale_de)
    )
    assert percent_published == int(1 / total * 100)


@run_on_commit
def test_duplicate_segments_in_rich_text_are_counted_per_segment(
    _on_commit, locale_en, locale_de
):
    """Repeated text in one rich text field yields two segments, one translation.

    get_progress() counts segments; counting StringTranslation rows instead
    (StringSegmentQuerySet.get_translations) collapses the pair and reports 66%
    published on fully published content, forever.
    """
    snippet = RichTextSnippet.objects.create(
        locale=locale_en, body="<p>Hello</p><p>World</p><p>Hello</p>"
    )
    source, _ = TranslationSource.get_or_create_from_instance(snippet)
    segments = StringSegment.objects.filter(source=source)
    assert segments.count() == 3
    assert segments.values("context_id", "string_id").distinct().count() == 2, (
        "two of these three segments must share a (context, string) pair"
    )

    translation, _ = Translation.objects.get_or_create(
        source=source, target_locale=locale_de
    )
    for segment in segments:
        StringTranslation.objects.update_or_create(
            translation_of_id=segment.string_id,
            context_id=segment.context_id,
            locale=locale_de,
            defaults={"data": f"DE {segment.string.data}"},
        )
    translation.save_target(publish=True)

    target = target_of(snippet, locale_de)
    total, translated = translation.get_progress()
    percent_translated, percent_published = get_translation_progress(
        snippet, locale_de, target
    )

    assert total == 3
    assert percent_translated == int(translated / total * 100) == 100
    assert percent_published == percent_translated, (
        "published must count segments, not StringTranslation rows"
    )
    assert "DE Hello" in target.body, "the duplicate really is published"


@run_on_commit
def test_translations_with_errors_are_not_counted(
    _on_commit, page_translation, locale_de
):
    page, source, translation = page_translation
    paths = segment_paths(source)
    translate_segment(source, locale_de, paths[0], "DE ok")
    translate_segment(source, locale_de, paths[1], "DE bad", has_error=True)
    translation.save_target(publish=True)

    total, translated = translation.get_progress()
    assert translated == 1, "get_progress ignores has_error rows"

    __, percent_published = get_translation_progress(
        page, locale_de, target_of(page, locale_de)
    )
    assert percent_published == int(1 / total * 100)


@run_on_commit
def test_draft_push_to_a_live_page_counts_as_published(
    _on_commit, page_translation, locale_de
):
    """save_target(publish=False) on a live page still writes to the live row.

    create_or_update_translation calls translation.save() before the `if publish`
    branch, so for a Page that is already live the new translations are served
    immediately even though the revision is not published. Counting them is
    correct. Do not narrow the marker by TranslationLog.revision to "fix" this -
    it would report live content as unpublished.
    """
    page, source, translation = page_translation
    paths = segment_paths(source)
    translate_segment(source, locale_de, paths[0], "DE first")
    translation.save_target(publish=True)

    translate_segment(source, locale_de, paths[1], "DE second")
    translation.save_target(publish=False)

    target = target_of(page, locale_de)
    assert target.live is True

    percent_translated, percent_published = get_translation_progress(
        page, locale_de, target
    )
    assert percent_published == percent_translated


@run_on_commit
def test_never_pushed_reports_zero(_on_commit, page_translation, locale_de):
    page, source, _translation = page_translation
    translate_segment(source, locale_de, segment_paths(source)[0], "DE only")

    assert not TranslationLog.objects.filter(source=source, locale=locale_de).exists()
    percent_translated, percent_published = get_translation_progress(
        page, locale_de, None
    )
    assert percent_translated > 0
    assert percent_published == 0


@run_on_commit
def test_unpublished_target_reports_zero(_on_commit, page_translation, locale_de):
    page, source, translation = page_translation
    translate_segment(source, locale_de, segment_paths(source)[0], "DE only")
    translation.save_target(publish=True)

    target = target_of(page, locale_de)
    assert target.live is True, "must actually be live before we unpublish it"
    target.unpublish()
    target.refresh_from_db()
    assert target.live is False

    percent_translated, percent_published = get_translation_progress(
        page, locale_de, target
    )
    assert percent_translated > 0
    assert percent_published == 0


def test_zero_segments_reports_fully_published(locale_en, locale_de):
    snippet = SampleSnippet.objects.create(locale=locale_en, heading="", desc="")
    source, __ = TranslationSource.get_or_create_from_instance(snippet)
    translation, __ = Translation.objects.get_or_create(
        source=source, target_locale=locale_de
    )
    total, _ = translation.get_progress()
    assert total == 0, "this test only means anything with no segments"

    assert get_translation_progress(snippet, locale_de, None) == (100, 100)


def test_no_translation_returns_none(test_page, locale_de):
    assert get_translation_progress(test_page, locale_de, None) is None


@run_on_commit
def test_non_draft_state_snippet_is_not_gated(_on_commit, locale_en, locale_de):
    """SampleSnippet has no DraftStateMixin, so there is no `live` to gate on."""
    snippet = SampleSnippet.objects.create(
        locale=locale_en, heading="Heading", desc="Desc"
    )
    source, __ = TranslationSource.get_or_create_from_instance(snippet)
    translation, __ = Translation.objects.get_or_create(
        source=source, target_locale=locale_de
    )
    for path in segment_paths(source):
        translate_segment(source, locale_de, path, f"DE {path}")
    translation.save_target(publish=True)

    target = target_of(snippet, locale_de)
    assert not hasattr(target, "live")

    percent_translated, percent_published = get_translation_progress(
        snippet, locale_de, target
    )
    assert percent_published == percent_translated


@run_on_commit
def test_draft_state_snippet_that_is_live_is_counted(_on_commit, locale_en, locale_de):
    snippet = DraftStateSnippet.objects.create(locale=locale_en, title="Title")
    source, __ = TranslationSource.get_or_create_from_instance(snippet)
    translation, __ = Translation.objects.get_or_create(
        source=source, target_locale=locale_de
    )
    for path in segment_paths(source):
        translate_segment(source, locale_de, path, f"DE {path}")
    translation.save_target(publish=True)

    target = target_of(snippet, locale_de)
    assert target.live is True

    percent_translated, percent_published = get_translation_progress(
        snippet, locale_de, target
    )
    assert percent_published == percent_translated


@run_on_commit
def test_draft_state_snippet_pushed_as_draft_reports_zero(
    _on_commit, locale_en, locale_de
):
    """Unlike a Page, the snippet branch sets live = publish."""
    snippet = DraftStateSnippet.objects.create(locale=locale_en, title="Title")
    source, __ = TranslationSource.get_or_create_from_instance(snippet)
    translation, __ = Translation.objects.get_or_create(
        source=source, target_locale=locale_de
    )
    for path in segment_paths(source):
        translate_segment(source, locale_de, path, f"DE {path}")
    translation.save_target(publish=False)

    target = target_of(snippet, locale_de)
    assert target.live is False

    percent_translated, percent_published = get_translation_progress(
        snippet, locale_de, target
    )
    assert percent_translated > 0
    assert percent_published == 0


@run_on_commit
def test_published_never_exceeds_translated(_on_commit, page_translation, locale_de):
    page, source, translation = page_translation
    for path in segment_paths(source):
        translate_segment(source, locale_de, path, f"DE {path}")
    translation.save_target(publish=True)

    target = target_of(page, locale_de)
    assert target.live is True
    percent_translated, percent_published = get_translation_progress(
        page, locale_de, target
    )
    assert percent_published <= percent_translated


@pytest.fixture
def fully_published_page(test_page, locale_es):
    """A page translated into Spanish, every segment translated and pushed live."""
    source, __ = TranslationSource.get_or_create_from_instance(test_page)
    translation, __ = Translation.objects.get_or_create(
        source=source, target_locale=locale_es
    )
    for path in segment_paths(source):
        translate_segment(source, locale_es, path, f"ES {path}")
    # Fixtures are resolved before the test function's @run_on_commit decorator
    # takes effect, so the patch has to be entered here as well.
    with run_on_commit:
        translation.save_target(publish=True)
    return test_page, source, translation


@run_on_commit
def test_editing_a_translation_after_publishing_decreases_published_percentage(
    _on_commit, fully_published_page, locale_es
):
    """Translate everything, publish, then revise one field and don't publish.

    Note has_unpublished_changes stays False throughout - editing a
    StringTranslation touches the translation store and (for the title path
    only) draft_title, never the live row. That flag cannot detect this, which
    is why the feature exists.
    """
    page, source, translation = fully_published_page
    target = target_of(page, locale_es)
    assert get_translation_progress(page, locale_es, target) == (100, 100)

    translate_segment(source, locale_es, "title", "ES title REVISED")

    target.refresh_from_db()
    total, __ = translation.get_progress()
    percent_translated, percent_published = get_translation_progress(
        page, locale_es, target
    )
    assert percent_translated == 100
    assert percent_published == int((total - 1) / total * 100)
    assert percent_published < percent_translated
    assert target.title == "ES title", "the live row still holds the old title"
    assert target.draft_title == "ES title REVISED"
    assert target.has_unpublished_changes is False, (
        "exactly why has_unpublished_changes cannot drive this feature"
    )

    translation.save_target(publish=True)
    target.refresh_from_db()
    assert get_translation_progress(page, locale_es, target) == (100, 100)
    assert target.title == "ES title REVISED"


@run_on_commit
def test_editing_the_target_page_directly_does_not_affect_published_percentage(
    _on_commit, fully_published_page, locale_es
):
    """A draft edit made in the page editor does not count as an unpublished
    translation.

    The translation store is untouched and the last push still covers every
    segment, so 100% of the translations really are live. The unpublished draft
    is reported by the existing (live + draft) status badge, not by this feature.
    """
    page, _source, _translation = fully_published_page
    target = target_of(page, locale_es)
    assert get_translation_progress(page, locale_es, target) == (100, 100)

    target.title = "Manually edited, unpublished"
    target.save_revision()
    target.refresh_from_db()

    assert get_translation_progress(page, locale_es, target) == (100, 100)
    assert target.has_unpublished_changes is True


@run_on_commit
def test_rebuild_stores_percent_published_for_pages(
    _on_commit, page_translation, locale_de
):
    page, source, translation = page_translation
    paths = segment_paths(source)
    translate_segment(source, locale_de, paths[0], "DE first")
    translation.save_target(publish=True)
    translate_segment(source, locale_de, paths[1], "DE second")

    create_page_translation_progress(page)

    progress = TranslationProgress.objects.get(
        source_page=page, translated_page__locale=locale_de
    )
    total, translated = translation.get_progress()
    assert progress.percent_translated == int(translated / total * 100)
    assert progress.percent_published == int(1 / total * 100)


@run_on_commit
def test_rebuild_refreshes_percent_published_after_a_push(
    _on_commit, page_translation, locale_de
):
    page, source, translation = page_translation
    for path in segment_paths(source):
        translate_segment(source, locale_de, path, f"DE {path}")
    translation.save_target(publish=True)

    target = target_of(page, locale_de)
    target.unpublish()
    create_page_translation_progress(page)

    progress = TranslationProgress.objects.get(
        source_page=page, translated_page__locale=locale_de
    )
    assert progress.percent_published == 0

    target.refresh_from_db()
    target.get_latest_revision().publish()
    create_page_translation_progress(page)

    progress.refresh_from_db()
    assert progress.percent_published == progress.percent_translated


@run_on_commit
def test_fallback_source_branch_carries_percent_published(
    _on_commit, test_page, locale_en, locale_de, locale_fr
):
    """FR is translated from DE, not EN; the fallback must still set published."""
    source_en, _ = TranslationSource.get_or_create_from_instance(test_page)
    translation_de, _ = Translation.objects.get_or_create(
        source=source_en, target_locale=locale_de
    )
    for path in segment_paths(source_en):
        translate_segment(source_en, locale_de, path, f"DE {path}")
    translation_de.save_target(publish=True)

    de_page = target_of(test_page, locale_de)
    source_de, _ = TranslationSource.get_or_create_from_instance(de_page)
    translation_fr, _ = Translation.objects.get_or_create(
        source=source_de, target_locale=locale_fr
    )
    for path in segment_paths(source_de):
        translate_segment(source_de, locale_fr, path, f"FR {path}")
    translation_fr.save_target(publish=True)

    assert not Translation.objects.filter(
        source=source_en, target_locale=locale_fr
    ).exists(), "EN->FR must not exist, so the fallback branch is exercised"

    create_page_translation_progress(test_page)

    progress = TranslationProgress.objects.get(
        source_page=test_page, translated_page__locale=locale_fr
    )
    assert progress.percent_translated > 0
    assert progress.percent_published == progress.percent_translated


@override_settings(WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"])
@run_on_commit
def test_rebuild_stores_percent_published_for_snippets(
    _on_commit, locale_en, locale_de
):
    snippet = SampleSnippet.objects.create(
        locale=locale_en, heading="Heading", desc="Desc"
    )
    source, _ = TranslationSource.get_or_create_from_instance(snippet)
    translation, _ = Translation.objects.get_or_create(
        source=source, target_locale=locale_de
    )
    for path in segment_paths(source):
        translate_segment(source, locale_de, path, f"DE {path}")
    translation.save_target(publish=True)

    create_snippet_translation_progress(snippet)

    progress = SnippetTranslationProgress.objects.get(
        source_object_id=snippet.pk, translated_locale=locale_de
    )
    assert progress.percent_published == progress.percent_translated


@run_on_commit
def test_publishing_the_target_refreshes_percent_published_via_signals(
    _on_commit, page_translation, locale_de
):
    """The handlers must keep percent_published correct with no explicit rebuild."""
    page, source, translation = page_translation
    paths = segment_paths(source)
    total = len(paths)

    # The target page does not exist until the first push, and neither does the
    # progress row - create_page_translation_progress iterates get_translations().
    translate_segment(source, locale_de, paths[0], "DE first")
    translation.save_target(publish=True)

    progress = TranslationProgress.objects.get(
        source_page=page, translated_page__locale=locale_de
    )
    assert progress.percent_published == int(1 / total * 100), (
        "translation_log_saved_handler must have rebuilt after the push"
    )

    # A new translation arrives: string_translation_saved_handler must rebuild,
    # and the published percentage must be recalculated.
    translate_segment(source, locale_de, paths[1], "DE second")

    progress.refresh_from_db()
    assert progress.percent_translated == 100
    assert progress.percent_published == int(1 / total * 100), (
        "the second translation is not live yet"
    )

    # Pushing it must recalculate, again with no explicit rebuild call.
    translation.save_target(publish=True)

    progress.refresh_from_db()
    assert progress.percent_published == progress.percent_translated == 100


@pytest.mark.django_db(transaction=True)
def test_percent_published_is_correct_after_a_real_commit(test_page, locale_de):
    """The receiver must hold under real COMMIT semantics, not just a patched on_commit.

    Every other test here runs under run_on_commit, which fires callbacks inline.
    This one does not, so it is the only test that proves wagtail-localize's
    publish callback really does run before our rebuild callback at COMMIT.
    """
    source, __ = TranslationSource.get_or_create_from_instance(test_page)
    translation, __ = Translation.objects.get_or_create(
        source=source, target_locale=locale_de
    )
    paths = segment_paths(source)
    total = len(paths)
    translate_segment(source, locale_de, paths[0], "DE first")

    translation.save_target(publish=True)

    progress = TranslationProgress.objects.get(
        source_page=test_page, translated_page__locale=locale_de
    )
    assert progress.percent_published == int(1 / total * 100)
    assert progress.percent_translated == int(1 / total * 100)
