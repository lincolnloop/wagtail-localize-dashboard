"""Tests for suppressing no-op StringTranslation saves."""

import logging
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from wagtail_localize.models import (
    StringSegment,
    StringTranslation,
    Translation,
    TranslationSource,
)

from tests.helpers import (
    get_first_segment_translation,
    resave_first_segment_like_editor,
    run_on_commit,
    target_of,
    translate_all_segments_and_publish,
)
from wagtail_localize_dashboard.models import TranslationProgress
from wagtail_localize_dashboard.utils import get_translation_progress

pytestmark = [pytest.mark.django_db]


@run_on_commit
def test_noop_resave_does_not_create_a_published_gap(_on_commit, test_page, locale_de):
    source, __ = translate_all_segments_and_publish(test_page, locale_de)
    target = target_of(test_page, locale_de)
    assert target.live is True, "the on_commit patch must have published the target"

    before = get_translation_progress(test_page, locale_de, target)

    # Save the translation without making any changes.
    resave_first_segment_like_editor(source, locale_de)

    after = get_translation_progress(test_page, locale_de, target)
    assert after == before, (
        "re-saving a segment with identical text must not change the "
        f"published percentage: {before} became {after}"
    )


@run_on_commit
def test_rebuild_command_agrees_after_a_noop_resave(_on_commit, test_page, locale_de):
    """A site that rebuilds from the command, not from signals, must agree."""
    source, __ = translate_all_segments_and_publish(test_page, locale_de)
    row = TranslationProgress.objects.get(
        source_page=test_page, translated_page__locale=locale_de
    )
    before = (row.percent_translated, row.percent_published)

    with override_settings(WAGTAIL_LOCALIZE_DASHBOARD_AUTO_UPDATE=False):
        resave_first_segment_like_editor(source, locale_de)

    call_command("rebuild_translation_progress")

    row.refresh_from_db()
    assert (row.percent_translated, row.percent_published) == before, (
        "a rebuild after a no-op save must reproduce the pre-save numbers"
    )


@run_on_commit
def test_real_edit_still_drops_the_published_count(_on_commit, test_page, locale_de):
    source, __ = translate_all_segments_and_publish(test_page, locale_de)
    target = target_of(test_page, locale_de)
    total = StringSegment.objects.filter(source=source).count()

    __, published_before, __ = get_translation_progress(test_page, locale_de, target)

    resave_first_segment_like_editor(source, locale_de, data="DE genuinely different")

    __, published_after, has_unpublished_translations = get_translation_progress(
        test_page, locale_de, target
    )
    assert published_after == int((total - 1) / total * 100), (
        f"one of {total} segments was edited after the push, so exactly "
        f"{total - 1} should still count as live"
    )
    assert published_after < published_before
    assert has_unpublished_translations is True


@run_on_commit
def test_updated_at_is_preserved_only_when_nothing_changed(
    _on_commit, test_page, locale_de
):
    source, __ = translate_all_segments_and_publish(test_page, locale_de)
    before = get_first_segment_translation(source, locale_de).updated_at

    resave_first_segment_like_editor(source, locale_de)
    assert get_first_segment_translation(source, locale_de).updated_at == before

    resave_first_segment_like_editor(source, locale_de, data="DE genuinely different")
    assert get_first_segment_translation(source, locale_de).updated_at > before


@run_on_commit
def test_a_changed_editor_only_field_is_still_a_noop(
    _on_commit, test_page, locale_de, admin_user
):
    """The real editor always sends last_translated_by; it must not count."""
    source, __ = translate_all_segments_and_publish(test_page, locale_de)
    before = get_first_segment_translation(source, locale_de).updated_at

    resave_first_segment_like_editor(source, locale_de, user=admin_user)

    stored = get_first_segment_translation(source, locale_de)
    assert stored.updated_at == before
    assert stored.last_translated_by_id == admin_user.pk, (
        "the last_translated_by_id field must still be written"
    )


@run_on_commit
def test_has_error_flip_counts_as_a_change(_on_commit, test_page, locale_de):
    """has_error changes _count_published, so flipping it is not a no-op."""
    source, __ = translate_all_segments_and_publish(test_page, locale_de)
    target = target_of(test_page, locale_de)
    before = get_first_segment_translation(source, locale_de).updated_at
    __, published_before, __ = get_translation_progress(test_page, locale_de, target)

    resave_first_segment_like_editor(source, locale_de, has_error=True)

    assert get_first_segment_translation(source, locale_de).updated_at > before
    __, published_after, __ = get_translation_progress(test_page, locale_de, target)
    assert published_after < published_before


@run_on_commit
def test_validation_failure_resave_does_not_crash_or_hide_the_change(
    _on_commit, test_page, locale_de
):
    """StringTranslation.save() re-saves itself with update_fields=["has_error"]."""
    source, __ = translate_all_segments_and_publish(test_page, locale_de)
    before = get_first_segment_translation(source, locale_de).updated_at

    # A link the source string does not have makes validate_translation_links()
    # raise. Unbalanced or stray tags do not trip it; a link count mismatch does.
    resave_first_segment_like_editor(
        source, locale_de, data='DE <a href="http://example.com/">link</a>'
    )

    stored = get_first_segment_translation(source, locale_de)
    assert stored.has_error is True, "upstream must have flagged the bad markup"
    assert stored.updated_at > before, (
        "a save that set has_error is a real change and must not be reverted"
    )


@run_on_commit
def test_creating_a_translation_is_untouched(_on_commit, test_page, locale_de):
    source, __ = TranslationSource.get_or_create_from_instance(test_page)
    Translation.objects.get_or_create(source=source, target_locale=locale_de)
    segment = StringSegment.objects.filter(source=source).order_by("order").first()

    created_row, created = StringTranslation.objects.update_or_create(
        translation_of=segment.string,
        context=segment.context,
        locale=locale_de,
        defaults={"data": "DE new"},
    )

    assert created is True
    assert created_row.updated_at is not None


@run_on_commit
def test_post_save_tolerates_a_missing_stash(_on_commit, test_page, locale_de):
    """pre_save may not have run, or may have found no row to stash."""
    from wagtail_localize_dashboard.signals import (
        restore_updated_stringtranslation_at_on_noop,
    )

    source, __ = translate_all_segments_and_publish(test_page, locale_de)
    stored = get_first_segment_translation(source, locale_de)

    # Normally, the pre-save adds a _dashboard_previous_translation property,
    # but here we test the scenario that it did not, for whatever reason (for
    # example, a bulk save).
    assert not hasattr(stored, "_dashboard_previous_translation")
    # No error is raised when restore_updated_stringtranslation_at_on_noop aaa().
    restore_updated_stringtranslation_at_on_noop(
        StringTranslation, stored, created=False
    )

    # An explicit None, as when the row was deleted between pre_save and save.
    stored._dashboard_previous_translation = None
    # No error is raised when restore_updated_stringtranslation_at_on_noop aaa().
    restore_updated_stringtranslation_at_on_noop(
        StringTranslation, stored, created=False
    )


@run_on_commit
def test_raw_saves_are_skipped(_on_commit, test_page, locale_de):
    """loaddata fires both signals with raw=True and must not pay for a SELECT."""
    from wagtail_localize_dashboard.signals import remember_previous_stringtranslation

    source, __ = translate_all_segments_and_publish(test_page, locale_de)
    stored = get_first_segment_translation(source, locale_de)

    with CaptureQueriesContext(connection) as ctx:
        remember_previous_stringtranslation(StringTranslation, stored, raw=True)

    assert len(ctx) == 0
    assert stored._dashboard_previous_translation is None


@run_on_commit
def test_a_real_update_fields_save_leaves_the_timestamp_alone(
    _on_commit, test_page, locale_de
):
    """save(update_fields=...) excluding updated_at does not fire auto_now."""
    source, __ = translate_all_segments_and_publish(test_page, locale_de)
    stored = get_first_segment_translation(source, locale_de)
    before = stored.updated_at

    stored.tool_name = "probe"
    with CaptureQueriesContext(connection) as ctx:
        stored.save(update_fields=["tool_name"])

    reloaded = get_first_segment_translation(source, locale_de)
    assert reloaded.updated_at == before, "auto_now never fired, so nothing moved"
    assert reloaded.tool_name == "probe", "the field being saved must still be written"
    # Match UPDATEs only, and only against StringTranslation's own table.
    # remember_previous_stringtranslation's stash is a SELECT that names updated_at
    # in its column list, so a bare substring test over every captured query
    # matches it and fails on a correct implementation. The table name is read
    # from the model rather than written out.
    table = StringTranslation._meta.db_table
    timestamp_writes = [
        q
        for q in ctx.captured_queries
        if q["sql"].lstrip().upper().startswith("UPDATE")
        and table in q["sql"]
        and "updated_at" in q["sql"]
    ]
    assert timestamp_writes == [], (
        "the guard must suppress an UPDATE writing the value already stored"
    )


@run_on_commit
def test_the_receivers_cost_one_select_and_one_update(_on_commit, test_page, locale_de):
    """Pin the overhead on the receivers themselves."""
    from wagtail_localize_dashboard.signals import (
        remember_previous_stringtranslation,
        restore_updated_stringtranslation_at_on_noop,
    )

    source, __ = translate_all_segments_and_publish(test_page, locale_de)
    stored = get_first_segment_translation(source, locale_de)

    with CaptureQueriesContext(connection) as stash:
        remember_previous_stringtranslation(StringTranslation, stored)
    assert len(stash) == 1, "the stash is exactly one SELECT"

    # Mimic what DateTimeField.pre_save() does during a real save.
    stored.updated_at = timezone.now()

    with CaptureQueriesContext(connection) as restore:
        restore_updated_stringtranslation_at_on_noop(
            StringTranslation, stored, created=False
        )
    assert len(restore) == 1, "a no-op costs exactly one UPDATE"

    # A real edit: the stash is re-read, and nothing is written back.
    remember_previous_stringtranslation(StringTranslation, stored)
    stored.data = "DE genuinely different"
    stored.updated_at = timezone.now()
    with CaptureQueriesContext(connection) as real:
        restore_updated_stringtranslation_at_on_noop(
            StringTranslation, stored, created=False
        )
    assert len(real) == 0, "a real edit writes nothing back"


@run_on_commit
def test_the_stash_cost_is_linear_in_rows_saved(_on_commit, test_page, locale_de):
    """A PO import saves one row per changed segment and pays one SELECT each."""
    from wagtail_localize_dashboard.signals import remember_previous_stringtranslation

    source, __ = translate_all_segments_and_publish(test_page, locale_de)
    rows = list(StringTranslation.objects.filter(locale=locale_de))
    assert len(rows) > 1, "the fixture must have more than one segment to mean anything"

    with CaptureQueriesContext(connection) as ctx:
        for row in rows:
            remember_previous_stringtranslation(StringTranslation, row)

    assert len(ctx) == len(rows), "one SELECT per row, and no more"


@run_on_commit
def test_stored_progress_row_survives_a_noop_resave(_on_commit, test_page, locale_de):
    """What the dashboard actually renders is the cached row, not a live call."""
    source, __ = translate_all_segments_and_publish(test_page, locale_de)
    row = TranslationProgress.objects.get(
        source_page=test_page, translated_page__locale=locale_de
    )
    before = (
        row.percent_translated,
        row.percent_published,
        row.has_unpublished_translations,
    )

    resave_first_segment_like_editor(source, locale_de)

    row.refresh_from_db()
    after = (
        row.percent_translated,
        row.percent_published,
        row.has_unpublished_translations,
    )
    assert after == before, (
        "has_unpublished_translations is what to_dict() hands the template and "
        f"what draws the badge, so it belongs in the comparison: {before} "
        f"became {after}"
    )


@run_on_commit
def test_a_broken_stash_does_not_break_the_save(_on_commit, test_page, locale_de):
    source, __ = translate_all_segments_and_publish(test_page, locale_de)
    before = get_first_segment_translation(source, locale_de).updated_at

    with patch(
        "wagtail_localize_dashboard.signals.StringTranslation.objects.using",
        side_effect=RuntimeError("database on fire"),
    ):
        resave_first_segment_like_editor(source, locale_de)

    stored = get_first_segment_translation(source, locale_de)
    assert stored.updated_at > before, (
        "with no stash the timestamp stands, as it did before the receivers"
    )


@run_on_commit
def test_a_failed_restore_reports_the_failure_and_changes_nothing(
    _on_commit, test_page, locale_de, caplog
):
    """An UPDATE that cannot reach the database must log and return quietly."""
    from wagtail_localize_dashboard.signals import (
        remember_previous_stringtranslation,
        restore_updated_stringtranslation_at_on_noop,
    )

    source, __ = translate_all_segments_and_publish(test_page, locale_de)
    stored = get_first_segment_translation(source, locale_de)
    remember_previous_stringtranslation(StringTranslation, stored)
    stash = stored._dashboard_previous_translation
    assert stash is not None, "the stash must exist for the restore to attempt a write"

    # Stand in for what DateTimeField.pre_save() does during a real save.
    new_updated_at = timezone.now()
    stored.updated_at = new_updated_at

    with caplog.at_level(logging.ERROR, logger="wagtail_localize_dashboard.signals"):
        with patch(
            "wagtail_localize_dashboard.signals.StringTranslation.objects.using",
            side_effect=RuntimeError("database on fire"),
        ):
            restore_updated_stringtranslation_at_on_noop(
                StringTranslation, stored, created=False
            )

    assert stored.updated_at == new_updated_at, (
        "a failed UPDATE must leave the instance's timestamp alone, so that it "
        "still matches what the database holds"
    )
    assert "Error in restore_updated_stringtranslation_at_on_noop" in caplog.text, (
        "a swallowed exception nobody can see is indistinguishable from the "
        f"feature silently not working: {[r.getMessage() for r in caplog.records]}"
    )
    assert (
        get_first_segment_translation(source, locale_de).updated_at
        == stash["updated_at"]
    ), "the stored row must be untouched, since the write never happened"


@run_on_commit
def test_setting_enabled_disabled(_on_commit, test_page, locale_de):
    """Assert that WAGTAIL_LOCALIZE_DASHBOARD_PRESERVE_TIMESTAMP_ON_NOOP_SAVES is respected."""
    source, __ = translate_all_segments_and_publish(test_page, locale_de)
    before = get_first_segment_translation(source, locale_de).updated_at

    with override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_PRESERVE_TIMESTAMP_ON_NOOP_SAVES=True
    ):
        resave_first_segment_like_editor(source, locale_de)
    assert get_first_segment_translation(source, locale_de).updated_at == before, (
        "on by default: the timestamp is preserved"
    )

    with override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_PRESERVE_TIMESTAMP_ON_NOOP_SAVES=False
    ):
        resave_first_segment_like_editor(source, locale_de)

    assert get_first_segment_translation(source, locale_de).updated_at > before, (
        "off: the bump stands, exactly as it did before this feature existed"
    )


@run_on_commit
def test_dashboard_disabled_leaves_upstream_alone(_on_commit, test_page, locale_de):
    """The ENABLED=False must switch off every receiver this package adds."""
    source, __ = translate_all_segments_and_publish(test_page, locale_de)
    before = get_first_segment_translation(source, locale_de).updated_at

    with override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_ENABLED=True,
        WAGTAIL_LOCALIZE_DASHBOARD_PRESERVE_TIMESTAMP_ON_NOOP_SAVES=True,
    ):
        resave_first_segment_like_editor(source, locale_de)
    assert get_first_segment_translation(source, locale_de).updated_at == before

    with override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_ENABLED=False,
        WAGTAIL_LOCALIZE_DASHBOARD_PRESERVE_TIMESTAMP_ON_NOOP_SAVES=True,
    ):
        resave_first_segment_like_editor(source, locale_de)
    assert get_first_segment_translation(source, locale_de).updated_at > before, (
        "with the dashboard not enabled, the "
        "WAGTAIL_LOCALIZE_DASHBOARD_PRESERVE_TIMESTAMP_ON_NOOP_SAVES should be ignored"
    )


@run_on_commit
def test_noop_resave_does_not_create_a_gap_for_snippets(
    _on_commit, sample_snippet, locale_de
):
    source, __ = translate_all_segments_and_publish(sample_snippet, locale_de)
    target = target_of(sample_snippet, locale_de)

    before = get_translation_progress(sample_snippet, locale_de, target)
    assert before is not None, "the snippet must have a Translation to measure"

    resave_first_segment_like_editor(source, locale_de)

    after = get_translation_progress(sample_snippet, locale_de, target)
    assert after == before, f"{before} became {after} with no content change"
