import contextlib

import pytest
from django.db import transaction
from wagtail_localize.models import (
    StringSegment,
    StringTranslation,
    Translation,
    TranslationSource,
)

from tests.helpers import count_translation_progress_calls, create_or_replace_page


def translate_every_segment(source, locale):
    """Write a translation for each of source's segments, in order."""
    for segment in StringSegment.objects.filter(source=source).order_by("order"):
        StringTranslation.objects.update_or_create(
            translation_of=segment.string,
            context=segment.context,
            locale=locale,
            defaults={"data": f"translated {segment.context.path}"},
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


@pytest.mark.django_db(transaction=True)
def test_bulk_segment_saves_queue_one_rebuild_per_locale(page_source, locale_de):
    """Every segment of one page, written in one transaction, is one rebuild."""
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


@pytest.mark.django_db(transaction=True)
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


@pytest.mark.django_db(transaction=True)
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


@pytest.mark.django_db(transaction=True)
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


@pytest.mark.django_db(transaction=True)
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


@pytest.mark.django_db(transaction=True)
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


@pytest.mark.django_db(transaction=True)
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
