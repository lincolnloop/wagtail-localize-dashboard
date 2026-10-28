import contextlib

import pytest
from django.db import transaction
from django.test import override_settings
from wagtail_localize.models import (
    StringSegment,
    StringTranslation,
    Translation,
    TranslationSource,
)

from tests.helpers import (
    count_snippet_translation_progress_calls,
    count_translation_progress_calls,
    create_or_replace_page,
    run_on_commit,
    target_of,
)
from tests.models import RichTextSnippet
from wagtail_localize_dashboard.models import TranslationProgress
from wagtail_localize_dashboard.signals import snippet_saved_handler
from wagtail_localize_dashboard.utils import get_translation_progress

pytestmark = [pytest.mark.django_db(transaction=True)]


def translate_segments(source, locale, segments):
    """Write a translation for each of the given segments."""
    for segment in segments:
        StringTranslation.objects.update_or_create(
            translation_of=segment.string,
            context=segment.context,
            locale=locale,
            defaults={"data": f"translated {segment.context.path}"},
        )


def translate_every_segment(source, locale):
    """Write a translation for each of source's segments, in order."""
    translate_segments(
        source, locale, StringSegment.objects.filter(source=source).order_by("order")
    )


def get_segment_count(source):
    return StringSegment.objects.filter(source=source).count()


@pytest.fixture
def page_source(home_page, locale_de):
    """A page with a German Translation, nothing translated yet."""
    page = create_or_replace_page(home_page, "bulk-save-page")
    source, __ = TranslationSource.get_or_create_from_instance(page)
    Translation.objects.get_or_create(source=source, target_locale=locale_de)
    assert get_segment_count(source) > 1, (
        f"this page has {get_segment_count(source)} segment(s) and needs more than "
        "one, or there is no bulk to batch"
    )
    return page, source


def test_bulk_segment_saves_collapse_into_one_rebuild_per_locale(
    page_source, locale_de
):
    """Every segment of one page, written in one transaction, is one rebuild per locale."""
    __, source = page_source
    locales = [locale_de]

    with count_translation_progress_calls() as calls:  # noqa: SIM117 (on separate lines here for readability)
        with transaction.atomic():
            for locale in locales:
                translate_every_segment(source, locale)

    assert calls["n"] == len(locales), (
        f"writing {get_segment_count(source)} segments into {len(locales)} locale(s) "
        f"in one transaction ran {calls['n']} rebuilds; expected: {len(locales)}"
    )


def test_a_rolled_back_rebuild_does_not_suppress_the_next_one(page_source, locale_de):
    """A key from a transaction that never committed must not block a later one."""
    __, source = page_source

    with count_translation_progress_calls() as calls:
        with contextlib.suppress(RuntimeError):  # noqa: SIM117 (on separate lines here for readability)
            with transaction.atomic():
                translate_every_segment(source, locale_de)
                raise RuntimeError("roll this transaction back")

        assert calls["n"] == 0, (
            f"{calls['n']} rebuilds ran for a transaction that rolled back"
        )

        with transaction.atomic():
            translate_every_segment(source, locale_de)

    assert calls["n"] == 1, (
        f"{calls['n']} rebuilds ran after the rollback; the work done in the "
        "second transaction must still be rebuilt exactly once"
    )


def test_a_rolled_back_savepoint_does_not_suppress_the_next_rebuild(
    page_source, locale_de
):
    """A nested atomic that raises must take its queued rebuild with it."""
    __, source = page_source

    with count_translation_progress_calls() as calls:  # noqa: SIM117 (on separate lines here for readability)
        with transaction.atomic():
            with contextlib.suppress(RuntimeError):  # noqa: SIM117 (on separate lines here for readability)
                with transaction.atomic():
                    translate_every_segment(source, locale_de)
                    raise RuntimeError("roll this savepoint back")

            translate_every_segment(source, locale_de)

    assert calls["n"] == 1, (
        f"{calls['n']} rebuilds ran; the savepoint's rebuild is gone with the "
        "savepoint, and the write that followed it needs one of its own"
    )


def test_a_rolled_back_duplicate_does_not_cancel_the_rebuild_before_it(
    page_source, locale_de
):
    """
    A savepoint takes its own rebuild with it, and nothing else.

    Duplicates queued in one transaction collapse into whichever of them runs
    first, so the one that outlives a rolled-back savepoint still does the work.
    """
    __, source = page_source

    with count_translation_progress_calls() as calls:  # noqa: SIM117 (on separate lines here for readability)
        with transaction.atomic():
            translate_every_segment(source, locale_de)
            with contextlib.suppress(RuntimeError):  # noqa: SIM117 (on separate lines here for readability)
                with transaction.atomic():
                    translate_every_segment(source, locale_de)
                    raise RuntimeError("roll this savepoint back")

    assert calls["n"] == 1, (
        f"{calls['n']} rebuilds ran; the writes made before the savepoint are "
        "committed and need exactly one rebuild of their own"
    )


def test_autocommit_segment_saves_each_get_their_own_rebuild(page_source, locale_de):
    """One segment at a time, as an editor works, must rebuild every time."""
    __, source = page_source
    expected = get_segment_count(source)

    with count_translation_progress_calls() as calls:
        translate_every_segment(source, locale_de)

    assert calls["n"] == expected, (
        f"{expected} segments saved outside any transaction ran {calls['n']} "
        f"rebuilds; expected: {expected}"
    )


def test_rebuilds_for_different_locales_do_not_collapse(
    page_source, locale_de, locale_es
):
    """Two locales are two different rebuilds, however they are batched."""
    __, source = page_source
    locales = [locale_de, locale_es]
    for locale in locales:
        Translation.objects.get_or_create(source=source, target_locale=locale)

    with count_translation_progress_calls() as calls:  # noqa: SIM117 (on separate lines here for readability)
        with transaction.atomic():
            for locale in locales:
                translate_every_segment(source, locale)

    assert calls["n"] == len(locales), (
        f"{calls['n']} rebuilds ran for {len(locales)} locales; each locale's "
        "progress is a separate row and needs its own rebuild"
    )


def test_a_source_save_is_not_collapsed_into_a_target_rebuild(page_source, locale_de):
    page, source = page_source
    locales = [locale_de]

    with count_translation_progress_calls() as calls:  # noqa: SIM117 (on separate lines here for readability)
        with transaction.atomic():
            translate_every_segment(source, locale_de)
            page.title = "A new title"
            page.save()

    locales_asked_for = [kwargs.get("only_locale") for kwargs in calls["kwargs"]]
    assert None in locales_asked_for, (
        f"the rebuilds asked for {locales_asked_for}; saving the source page "
        "must still rebuild every locale, not just the one being translated"
    )
    assert calls["n"] > len(locales)


def test_another_apps_pending_callback_does_not_break_the_scan(page_source):
    """The queue is shared; reading .key off somebody else's callback crashes."""
    page, __ = page_source
    ran = []

    with count_translation_progress_calls() as calls:  # noqa: SIM117 (on separate lines here for readability)
        with transaction.atomic():
            transaction.on_commit(lambda: ran.append("another app"))
            page.title = "Saved once"
            page.save()
            page.title = "Saved twice"
            page.save()

    assert ran == ["another app"], (
        "the other callback must still run; the scan only reads the queue"
    )
    page.refresh_from_db()
    assert page.title == "Saved twice"
    assert calls["n"] == 1, (
        f"{calls['n']} rebuilds ran for two saves of one page queued beside "
        "another app's callback; the duplicate must be skipped without reading "
        "attributes off a callback that is not ours"
    )


@pytest.fixture
def published_page_source_with_de_translation(home_page, locale_de):
    """A page with a published German target, so a progress row is stored."""
    page = create_or_replace_page(home_page, "capture-block-page")
    source, __ = TranslationSource.get_or_create_from_instance(page)
    translation, __ = Translation.objects.get_or_create(
        source=source, target_locale=locale_de
    )
    with run_on_commit:
        translation.save_target(publish=True)
    assert get_segment_count(source) > 1, (
        f"this page has {get_segment_count(source)} segment(s) and needs more than "
        "one, or there is nothing to write on either side of a capture block"
    )
    return page, source


def get_stored_and_live_progress(page, locale):
    row = TranslationProgress.objects.get(
        source_page=page, translated_page__locale=locale
    )
    stored = (
        row.percent_translated,
        row.percent_published,
        row.has_unpublished_translations,
    )
    return stored, get_translation_progress(page, locale, target_of(page, locale))


# Not transaction=True, unlike the rest of this module: captureOnCommitCallbacks
# can only capture a callback that is queued, and autocommit runs them instead.
@pytest.mark.django_db(transaction=False)
def test_a_write_inside_a_capture_block_still_rebuilds_the_row(
    published_page_source_with_de_translation,
    locale_de,
    django_capture_on_commit_callbacks,
):
    """
    A rebuild queued before a capture block must not swallow the one inside it.

    This test exists to handle this scenario:
    captureOnCommitCallbacks collects only the callbacks registered after its
    block opens, and a TestCase never commits, so a rebuild queued while a
    downstream test was arranging stays pending for the rest of that test. Every
    save has to register a callback of its own, or the test reads a progress row
    that execute=True never rebuilt.
    """
    page, source = published_page_source_with_de_translation
    segments = list(StringSegment.objects.filter(source=source).order_by("order"))

    # Arrange outside the block, the way a downstream test's setup might.
    translate_segments(source, locale_de, segments[:1])

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        translate_segments(source, locale_de, segments[1:])

    assert callbacks, (
        "the writes inside the block registered no callback, so there was "
        "nothing for execute=True to run"
    )
    stored, live = get_stored_and_live_progress(page, locale_de)
    assert stored == live, (
        f"the stored row says {stored} and a fresh calculation says {live}; the "
        "rebuild for the writes made inside the block did not run"
    )


# Not transaction=True, unlike the rest of this module: captureOnCommitCallbacks
# can only capture a callback that is queued, and autocommit runs them instead.
@pytest.mark.django_db(transaction=False)
def test_each_capture_block_gets_its_own_rebuild(
    published_page_source_with_de_translation,
    locale_de,
    django_capture_on_commit_callbacks,
):
    """A second block writes segments the first did not, and needs its own rebuild."""
    __, source = published_page_source_with_de_translation
    segments = list(StringSegment.objects.filter(source=source).order_by("order"))
    blocks = [segments[:1], segments[1:]]

    with count_translation_progress_calls() as calls:
        for written in blocks:
            with django_capture_on_commit_callbacks(execute=True):
                translate_segments(source, locale_de, written)

    assert calls["n"] == len(blocks), (
        f"{len(blocks)} capture blocks ran {calls['n']} rebuilds; the record of "
        "what has already been rebuilt belongs to one commit, not to the test"
    )


@pytest.fixture
def snippet_source(locale_en, locale_de):
    """A tracked snippet of several segments, with a German Translation."""
    snippet = RichTextSnippet.objects.create(
        locale=locale_en,
        body=(
            "<p>The first paragraph.</p><p>The second paragraph.</p>"
            "<p>The third paragraph.</p><p>The fourth paragraph.</p>"
        ),
    )
    source, __ = TranslationSource.get_or_create_from_instance(snippet)
    Translation.objects.get_or_create(source=source, target_locale=locale_de)
    assert get_segment_count(source) > 2, (
        f"this snippet has {get_segment_count(source)} segment(s) and needs more "
        "than two, or it is no better a bulk than the page fixture"
    )
    return snippet, source


@override_settings(
    WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.RichTextSnippet"]
)
def test_bulk_snippet_segment_saves_collapse_into_one_rebuild_per_locale(
    snippet_source, locale_de
):
    """A snippet imported in one transaction is one rebuild, as a page is."""
    __, source = snippet_source
    locales = [locale_de]

    with count_snippet_translation_progress_calls() as calls:  # noqa: SIM117 (on separate lines here for readability)
        with transaction.atomic():
            for locale in locales:
                translate_every_segment(source, locale)

    assert calls["n"] == len(locales), (
        f"writing {get_segment_count(source)} snippet segments into "
        f"{len(locales)} locale(s) in one transaction ran {calls['n']} "
        f"rebuilds; expected: {len(locales)}"
    )


@override_settings(
    WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.RichTextSnippet"]
)
def test_a_page_rebuild_and_a_snippet_rebuild_never_collapse(
    page_source, snippet_source, locale_de
):
    """Both kinds of rebuild share one queue; neither may swallow the other."""
    __, page_translation_source = page_source
    __, snippet_translation_source = snippet_source

    with (  # noqa: SIM117 (on separate lines here for readability)
        count_translation_progress_calls() as page_calls,
        count_snippet_translation_progress_calls() as snippet_calls,
    ):
        with transaction.atomic():
            translate_every_segment(page_translation_source, locale_de)
            translate_every_segment(snippet_translation_source, locale_de)

    assert page_calls["n"] == 1, (
        f"{page_calls['n']} page rebuilds ran; the page needs exactly one"
    )
    assert snippet_calls["n"] == 1, (
        f"{snippet_calls['n']} snippet rebuilds ran; the snippet needs exactly "
        "one, and must not be skipped because a page rebuild is queued"
    )


def test_repeated_snippet_saves_collapse_into_one_rebuild(snippet_source):
    """Saving one snippet twice in a transaction is one rebuild at commit."""
    snippet, __ = snippet_source
    saves = 2

    with count_snippet_translation_progress_calls() as calls:  # noqa: SIM117 (on separate lines here for readability)
        with transaction.atomic():
            for __ in range(saves):
                snippet_saved_handler(type(snippet), snippet, created=False)

    assert calls["n"] == 1, (
        f"{saves} saves of one snippet in one transaction ran {calls['n']} "
        "rebuilds; expected: 1 (since both saves had an identical snippet)"
    )
