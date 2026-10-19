import logging
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from django.test import override_settings
from wagtail_localize.models import (
    StringSegment,
    StringTranslation,
    Translation,
    TranslationLog,
    TranslationSource,
)

import wagtail_localize_dashboard.signals as dashboard_signals
from tests.helpers import create_or_replace_page, run_on_commit
from tests.models import SampleSnippet

pytestmark = [pytest.mark.django_db]

HANDLERS = [
    "translation_saved_handler",
    "string_translation_saved_handler",
    "string_translation_deleted_handler",
    "translation_log_saved_handler",
    "translation_source_saved_handler",
]

TRACK_SAMPLE_SNIPPET = override_settings(
    WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
)


@contextmanager
def set_up_progress_calls_recording():
    """Record which builder was reached, and with which object."""
    calls = {"page": [], "snippet": []}
    with (
        patch.object(
            dashboard_signals,
            "create_page_translation_progress",
            lambda obj, **kwargs: calls["page"].append(obj),
        ),
        patch.object(
            dashboard_signals,
            "create_snippet_translation_progress",
            lambda obj, **kwargs: calls["snippet"].append(obj),
        ),
    ):
        yield calls


def set_up_triggering_write_function(handler, source_object, locale):
    """Set up for one handler, and return the write that triggers it."""
    source, __ = TranslationSource.get_or_create_from_instance(source_object)

    if handler == "translation_source_saved_handler":
        return source.save

    if handler == "translation_saved_handler":
        return lambda: Translation.objects.create(source=source, target_locale=locale)

    Translation.objects.get_or_create(source=source, target_locale=locale)

    if handler == "translation_log_saved_handler":
        return lambda: TranslationLog.objects.create(source=source, locale=locale)

    segment = StringSegment.objects.filter(source=source).order_by("order").first()

    if handler == "string_translation_saved_handler":
        return lambda: StringTranslation.objects.create(
            translation_of=segment.string,
            context=segment.context,
            locale=locale,
            data="translated",
        )

    if handler == "string_translation_deleted_handler":
        stored = StringTranslation.objects.create(
            translation_of=segment.string,
            context=segment.context,
            locale=locale,
            data="translated",
        )
        return stored.delete

    raise ValueError(f"no setup written for {handler}")


@pytest.mark.parametrize("handler", HANDLERS)
@run_on_commit
def test_handler_rebuilds_the_page_it_was_given(
    _on_commit, handler, home_page, locale_de
):
    page = create_or_replace_page(home_page, "matrix-page")
    triggering_write = set_up_triggering_write_function(handler, page, locale_de)

    with set_up_progress_calls_recording() as calls:
        triggering_write()

    assert [obj.pk for obj in calls["page"]] == [page.pk], (
        f"{handler} rebuilt {calls['page']}, expected exactly [{page.pk}]"
    )
    assert calls["snippet"] == [], f"{handler} also rebuilt a snippet"


@pytest.mark.parametrize("handler", HANDLERS)
@TRACK_SAMPLE_SNIPPET
@run_on_commit
def test_handler_rebuilds_the_tracked_snippet_it_was_given(
    _on_commit, handler, locale_en, locale_de
):
    snippet = SampleSnippet.objects.create(locale=locale_en, heading="Matrix")
    triggering_write = set_up_triggering_write_function(handler, snippet, locale_de)

    with set_up_progress_calls_recording() as calls:
        triggering_write()

    assert [obj.pk for obj in calls["snippet"]] == [snippet.pk], (
        f"{handler} rebuilt {calls['snippet']}, expected exactly [{snippet.pk}]"
    )
    assert calls["page"] == [], f"{handler} also rebuilt a page"


@pytest.mark.parametrize("handler", HANDLERS)
@run_on_commit
def test_handler_ignores_an_untracked_snippet(
    _on_commit, handler, locale_en, locale_de
):
    snippet = SampleSnippet.objects.create(locale=locale_en, heading="Matrix")
    triggering_write = set_up_triggering_write_function(handler, snippet, locale_de)

    with set_up_progress_calls_recording() as calls:
        triggering_write()

    assert calls == {"page": [], "snippet": []}, (
        f"{handler} rebuilt {calls} for a snippet nobody asked to track"
    )


@pytest.mark.parametrize("handler", HANDLERS)
@override_settings(WAGTAIL_LOCALIZE_DASHBOARD_TRACK_PAGES=False)
@run_on_commit
def test_handler_does_not_rebuild_pages_when_track_pages_is_off(
    _on_commit, handler, home_page, locale_de
):
    page = create_or_replace_page(home_page, "matrix-page")
    triggering_write = set_up_triggering_write_function(handler, page, locale_de)

    with set_up_progress_calls_recording() as calls:
        triggering_write()

    assert calls == {"page": [], "snippet": []}, (
        f"{handler} rebuilt a page with TRACK_PAGES off"
    )


@pytest.mark.parametrize("handler", HANDLERS)
@override_settings(WAGTAIL_LOCALIZE_DASHBOARD_AUTO_UPDATE=False)
@run_on_commit
def test_handler_does_nothing_when_auto_update_is_off(
    _on_commit, handler, home_page, locale_de
):
    page = create_or_replace_page(home_page, "matrix-page")
    triggering_write = set_up_triggering_write_function(handler, page, locale_de)

    with set_up_progress_calls_recording() as calls:
        triggering_write()

    assert calls == {"page": [], "snippet": []}, (
        f"{handler} rebuilt {calls} with AUTO_UPDATE off"
    )


@pytest.mark.parametrize(
    "handler",
    ["string_translation_saved_handler", "string_translation_deleted_handler"],
)
@run_on_commit
def test_the_string_handlers_do_nothing_without_a_segment(
    _on_commit, handler, home_page, locale_de, caplog
):
    """A StringTranslation whose segment is gone resolves to no source object."""
    page = create_or_replace_page(home_page, "matrix-page")
    source, __ = TranslationSource.get_or_create_from_instance(page)
    Translation.objects.get_or_create(source=source, target_locale=locale_de)
    segment = StringSegment.objects.filter(source=source).order_by("order").first()
    string, context = segment.string, segment.context
    StringSegment.objects.filter(source=source).delete()

    def write():
        return StringTranslation.objects.create(
            translation_of=string, context=context, locale=locale_de, data="t"
        )

    with caplog.at_level(logging.ERROR, logger="wagtail_localize_dashboard.signals"):
        if handler == "string_translation_saved_handler":
            with set_up_progress_calls_recording() as calls:
                write()
        else:
            stored = write()
            with set_up_progress_calls_recording() as calls:
                stored.delete()

    assert calls == {"page": [], "snippet": []}, (
        f"{handler} rebuilt {calls} for a StringTranslation with no segment"
    )
    # A handler that uses the missing segment and crashes also rebuilds
    # nothing, so the log is the only thing that tells the two apart.
    assert caplog.records == [], [r.getMessage() for r in caplog.records]
