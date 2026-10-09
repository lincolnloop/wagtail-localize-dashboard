"""
Cost regression tests for multi-locale translation work.
"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from wagtail.models import Locale, Page
from wagtail_localize.models import (
    StringSegment,
    StringTranslation,
    Translation,
    TranslationSource,
)

from tests.helpers import (
    count_translation_progress_calls,
    create_or_replace_page,
    ensure_home_page,
)

FIVE_LOCALE_CODES = ["de", "es", "fr", "it", "nl"]
TEN_LOCALE_CODES = [*FIVE_LOCALE_CODES, "pt", "pl", "sv", "da", "fi"]

# The ceilings for calling our rebuilding functions, per locale count.
MAX_REBUILD_CALLS = {
    5: 41,  # For 5 locales, there can be a maxium of 41 calls
    10: 81,  # For 10 locales, there can be a maxium of 81 calls
}
MAX_SEGMENT_SAVE_REBUILDS_BY_LOCALE_COUNT = {
    1: 2,  # For 5 locales, there can be a maxium of 2 calls
    10: 2,  # For 10 locales, there can be a maxium of 2 calls
}

TIMESTAMPS = {"last_updated", "created_at"}


def _warm_up():
    """Translate the shared page tree into every locale before measuring."""
    home = ensure_home_page()
    if (
        Page.objects.filter(translation_key=home.translation_key).count()
        >= len(TEN_LOCALE_CODES) + 1
    ):
        return

    for code in TEN_LOCALE_CODES:
        Locale.objects.get_or_create(language_code=code)
    page = create_or_replace_page(home, "warm-up-page")
    source, __ = TranslationSource.get_or_create_from_instance(page)
    for code in TEN_LOCALE_CODES:
        translation, __ = Translation.objects.get_or_create(
            source=source, target_locale=Locale.objects.get(language_code=code)
        )
        translation.save_target(publish=True)


def _assert_log_did_not_overflow():
    """connection.queries_log is a bounded deque; a full one is not a count.

    Django clears it once per test, not between measurements. If it fills, the
    next measurement reports maxlen minus whatever was already logged, which
    looks like a plausible number and is not one.
    """
    log = connection.queries_log
    assert len(log) < log.maxlen, (
        f"the query log reached its {log.maxlen}-entry ceiling, so this "
        "measurement is a truncation artifact rather than a query count; "
        "clear the log before each measurement"
    )


def _submit(locales, slug="budget-page"):
    """Measure one page submitted and published into `locales`."""
    _warm_up()
    home = ensure_home_page()
    for code in locales:
        Locale.objects.get_or_create(language_code=code)
    page = create_or_replace_page(home, slug)

    connection.queries_log.clear()
    with (
        count_translation_progress_calls() as calls,
        CaptureQueriesContext(connection) as ctx,
    ):
        source, __ = TranslationSource.get_or_create_from_instance(page)
        for code in locales:
            locale = Locale.objects.get(language_code=code)
            translation, __ = Translation.objects.get_or_create(
                source=source, target_locale=locale
            )
            translation.save_target(publish=True)

    _assert_log_did_not_overflow()
    return calls["n"], len(ctx)


def _save_one_segment(locales, slug):
    """Publish into `locales`, then measure one segment save in the first one."""
    _submit(locales, slug=slug)
    page = Page.objects.get(slug=slug, locale__language_code="en")
    source = (
        TranslationSource.objects.filter(object_id=page.translation_key)
        .order_by("-created_at")
        .first()
    )
    locale = Locale.objects.get(language_code=locales[0])
    segment = StringSegment.objects.filter(source=source).order_by("order").first()
    assert segment is not None, "no segment to translate; the fixture is wrong"

    connection.queries_log.clear()
    with (
        count_translation_progress_calls() as calls,
        CaptureQueriesContext(connection) as ctx,
    ):
        StringTranslation.objects.update_or_create(
            translation_of=segment.string,
            context=segment.context,
            locale=locale,
            defaults={"data": "translated"},
        )

    _assert_log_did_not_overflow()
    return calls["n"], len(ctx)


@pytest.mark.django_db(transaction=True)
def test_submit_cost_grows_linearly_with_locale_count():
    """Submitting into twice as many locales must not cost more than twice as many calls."""
    rebuilds_5, queries_5 = _submit(FIVE_LOCALE_CODES, slug="budget-page-5")
    rebuilds_10, queries_10 = _submit(TEN_LOCALE_CODES, slug="budget-page-10")
    growth = queries_10 / queries_5

    assert rebuilds_5 <= MAX_REBUILD_CALLS[5], (
        f"{rebuilds_5} rebuilds for 5 locales, ceiling {MAX_REBUILD_CALLS[5]}"
    )
    assert rebuilds_10 <= MAX_REBUILD_CALLS[10], (
        f"{rebuilds_10} rebuilds for 10 locales, ceiling {MAX_REBUILD_CALLS[10]}"
    )
    assert growth <= 2, (
        f"doubling the locale count multiplied queries by {growth:.2f} "
        f"({queries_5} -> {queries_10}), which is more than a linear increase"
    )


@pytest.mark.django_db(transaction=True)
def test_one_segment_save_does_not_scale_with_locale_count():
    rebuilds_1, queries_1 = _save_one_segment(["de"], slug="segment-page-1")
    rebuilds_10, queries_10 = _save_one_segment(
        TEN_LOCALE_CODES, slug="segment-page-10"
    )
    growth = queries_10 / queries_1

    assert rebuilds_1 <= MAX_SEGMENT_SAVE_REBUILDS_BY_LOCALE_COUNT[1], (
        f"{rebuilds_1} rebuilds to save one segment with 1 locale, "
        f"ceiling {MAX_SEGMENT_SAVE_REBUILDS_BY_LOCALE_COUNT[1]}"
    )
    assert rebuilds_10 <= MAX_SEGMENT_SAVE_REBUILDS_BY_LOCALE_COUNT[10], (
        f"{rebuilds_10} rebuilds to save one segment with 10 locales, "
        f"ceiling {MAX_SEGMENT_SAVE_REBUILDS_BY_LOCALE_COUNT[10]}"
    )
    assert growth <= 2, (
        f"saving one segment cost {growth:.2f}x more with ten locales than "
        f"with one ({queries_1} -> {queries_10}); the other nine locales were "
        "not touched and must not be rebuilt"
    )
