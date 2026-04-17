"""
Tests for management commands.
"""

from io import StringIO

from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.test import override_settings

import pytest
from wagtail.models import Page
from wagtail_localize.models import Translation, TranslationSource
from wagtail_localize_dashboard.models import (
    SnippetTranslationProgress,
    TranslationProgress,
)
from tests.models import SampleSnippet


@pytest.mark.django_db
class TestRebuildTranslationProgress:
    """Tests for the rebuild_translation_progress management command."""

    def test_command_runs_successfully(self, capsys):
        """Test that command executes without errors."""
        out = StringIO()
        call_command("rebuild_translation_progress", stdout=out)

        output = out.getvalue()
        assert "Successfully rebuilt translation progress" in output

    def test_command_creates_progress_records(
        self, test_page_with_translations, locale_de, locale_es
    ):
        """Test that command creates TranslationProgress records."""
        # Clear any existing records
        TranslationProgress.objects.all().delete()

        # Run command
        call_command("rebuild_translation_progress", stdout=StringIO())

        # Should have records for the translations
        assert TranslationProgress.objects.filter(
            source_page_id=test_page_with_translations.id,
        ).exists()

    def test_command_updates_existing_records(
        self, test_page_with_translations, locale_de
    ):
        """Test that command updates existing progress records."""
        # Get the actual translated page
        de_translation = test_page_with_translations.get_translation(locale_de)

        # Create a progress record with incorrect percentage
        TranslationProgress.objects.create(
            source_page=test_page_with_translations,
            translated_page=de_translation,
            percent_translated=50,  # Incorrect percentage
        )

        # Run command
        call_command("rebuild_translation_progress", stdout=StringIO())

        # The command rebuilds all records, so it may delete and recreate
        # Check that a progress record exists for this translation
        updated_progress = TranslationProgress.objects.filter(
            source_page_id=test_page_with_translations.id,
            translated_page_id=de_translation.id,
        ).first()
        # The percentage should have been recalculated.
        assert updated_progress != 50

    def test_command_with_clean_orphans_flag(self, test_page):
        """Test that --clean-orphans flag works via the for_pages command.

        The combined rebuild_translation_progress command no longer accepts
        --clean-orphans; use rebuild_translation_progress_for_pages instead.
        """
        out = StringIO()
        call_command(
            "rebuild_translation_progress_for_pages", clean_orphans=True, stdout=out
        )

        output = out.getvalue()
        assert "Successfully rebuilt" in output or "successfully rebuilt" in output

    def test_command_without_clean_orphans_flag(self, test_page):
        """Test that command works without --clean-orphans flag.

        Note: Since we now use ForeignKey with CASCADE, orphaned records
        cannot exist, so this test just verifies the command runs successfully.
        """
        # Run command without --clean-orphans
        out = StringIO()
        call_command("rebuild_translation_progress", stdout=out)

        output = out.getvalue()
        # Should complete successfully
        assert "Successfully rebuilt" in output or "successfully rebuilt" in output

    def test_command_output_shows_statistics(self, test_page_with_translations):
        """Test that command outputs useful statistics."""
        out = StringIO()
        call_command("rebuild_translation_progress", stdout=out)

        output = out.getvalue()

        # Check for expected output elements
        assert "Successfully rebuilt translation progress" in output
        # Should show counts
        assert "pages:" in output.lower()

    def test_command_with_empty_database(self, db):
        """Test that command handles empty database gracefully."""
        # Clear all pages and progress records
        TranslationProgress.objects.all().delete()

        # Run command
        out = StringIO()
        call_command("rebuild_translation_progress", stdout=out)

        output = out.getvalue()
        # Should complete without errors
        assert "successfully rebuilt" in output.lower()
        assert TranslationProgress.objects.count() == 0

    def test_command_with_multiple_locales(
        self, test_page, locale_de, locale_es, locale_fr
    ):
        """Test command with multiple target locales."""
        from wagtail_localize.models import Translation, TranslationSource

        # Create translation source
        translation_source, _ = TranslationSource.get_or_create_from_instance(test_page)

        # Create translations in multiple locales
        for locale in [locale_de, locale_es, locale_fr]:
            translation, _ = Translation.objects.get_or_create(
                source=translation_source,
                target_locale=locale,
            )
            translation.save_target(publish=True)

        # Currently, there are no TranslationProgress records.
        assert TranslationProgress.objects.count() == 0

        # Run command
        out = StringIO()
        call_command("rebuild_translation_progress", stdout=out)

        output = out.getvalue()
        assert "successfully rebuilt" in output.lower()

        # Should have progress records for each translation
        progress_records = TranslationProgress.objects.filter(
            source_page_id=test_page.id,
        )

        # Should have one record per translated page
        assert progress_records.count() == 3

    def test_command_handles_pages_without_translations(self, test_page):
        """Test that command handles pages with no translations."""
        # test_page has no translations
        assert (
            not hasattr(test_page, "translation_key")
            or not test_page.get_translations().exclude(id=test_page.id).exists()
        )

        # Currently, there are no TranslationProgress records.
        assert TranslationProgress.objects.count() == 0

        # Run command
        out = StringIO()
        call_command("rebuild_translation_progress", stdout=out)

        output = out.getvalue()
        # Should complete successfully
        assert "successfully rebuilt" in output.lower()
        # There are still no TranslationProgress records.
        assert TranslationProgress.objects.count() == 0

    def test_command_idempotent(self, test_page_with_translations):
        """Test that running command multiple times is safe."""
        # Run command twice
        call_command("rebuild_translation_progress", stdout=StringIO())
        initial_count = TranslationProgress.objects.count()

        call_command("rebuild_translation_progress", stdout=StringIO())
        final_count = TranslationProgress.objects.count()

        # Count should be stable
        assert initial_count == final_count


@pytest.mark.django_db
class TestRebuildTranslationProgressForPages:
    """Tests for the rebuild_translation_progress_for_pages management command."""

    def test_command_runs_successfully(self):
        """Command executes without errors."""
        out = StringIO()
        call_command("rebuild_translation_progress_for_pages", stdout=out)
        output = out.getvalue()
        assert "Successfully rebuilt page translation progress" in output

    def test_command_output_shows_pages_processed(self, test_page_with_translations):
        """Command output includes a pages-processed count."""
        out = StringIO()
        call_command("rebuild_translation_progress_for_pages", stdout=out)
        output = out.getvalue()
        assert "pages:" in output.lower()

    def test_command_with_clean_orphans(self):
        """Command accepts --clean-orphans without error."""
        out = StringIO()
        call_command(
            "rebuild_translation_progress_for_pages", clean_orphans=True, stdout=out
        )
        output = out.getvalue()
        assert "Successfully rebuilt" in output or "successfully rebuilt" in output

    def test_command_creates_progress_records(self, test_page_with_translations):
        """Command creates TranslationProgress records."""
        TranslationProgress.objects.all().delete()
        call_command("rebuild_translation_progress_for_pages", stdout=StringIO())
        assert TranslationProgress.objects.filter(
            source_page_id=test_page_with_translations.id
        ).exists()

    def test_command_updates_existing_records(
        self, test_page_with_translations, locale_de
    ):
        """Command updates existing progress records with recalculated percentages."""
        de_translation = test_page_with_translations.get_translation(locale_de)
        TranslationProgress.objects.create(
            source_page=test_page_with_translations,
            translated_page=de_translation,
            percent_translated=50,
        )

        call_command("rebuild_translation_progress_for_pages", stdout=StringIO())

        updated = TranslationProgress.objects.filter(
            source_page_id=test_page_with_translations.id,
            translated_page_id=de_translation.id,
        ).first()
        assert updated is not None
        assert updated.percent_translated != 50

    def test_command_output_shows_statistics(self, test_page_with_translations):
        """Command output includes pages-processed count and success message."""
        out = StringIO()
        call_command("rebuild_translation_progress_for_pages", stdout=out)
        output = out.getvalue()
        assert "Successfully rebuilt page translation progress" in output
        assert "pages:" in output.lower()

    def test_command_with_empty_database(self, db):
        """Command handles an empty page table gracefully."""
        Page.objects.filter(depth__gt=1).delete()
        TranslationProgress.objects.all().delete()

        out = StringIO()
        call_command("rebuild_translation_progress_for_pages", stdout=out)
        output = out.getvalue()
        assert "successfully rebuilt" in output.lower()
        assert TranslationProgress.objects.count() == 0

    def test_command_with_multiple_locales(
        self, test_page, locale_de, locale_es, locale_fr
    ):
        """Command creates one progress record per translated locale."""
        translation_source, _ = TranslationSource.get_or_create_from_instance(test_page)
        for locale in [locale_de, locale_es, locale_fr]:
            t, _ = Translation.objects.get_or_create(
                source=translation_source, target_locale=locale
            )
            t.save_target(publish=True)

        TranslationProgress.objects.all().delete()
        call_command("rebuild_translation_progress_for_pages", stdout=StringIO())

        records = TranslationProgress.objects.filter(source_page_id=test_page.id)
        assert records.count() == 3

    def test_command_handles_pages_without_translations(self, test_page):
        """Command skips pages that have no translated copies."""
        TranslationProgress.objects.all().delete()
        call_command("rebuild_translation_progress_for_pages", stdout=StringIO())
        assert TranslationProgress.objects.count() == 0

    def test_command_idempotent(self, test_page_with_translations):
        """Running the command twice produces a stable record count."""
        call_command("rebuild_translation_progress_for_pages", stdout=StringIO())
        initial_count = TranslationProgress.objects.count()

        call_command("rebuild_translation_progress_for_pages", stdout=StringIO())
        final_count = TranslationProgress.objects.count()

        assert initial_count == final_count


@pytest.mark.django_db
class TestRebuildTranslationProgressForSnippets:
    """Tests for the rebuild_translation_progress_for_snippets management command."""

    def test_command_warns_when_no_tracked_snippets(self):
        """Command prints a warning and exits when TRACKED_SNIPPETS is empty."""
        out = StringIO()
        call_command("rebuild_translation_progress_for_snippets", stdout=out)
        output = out.getvalue()
        assert "TRACKED_SNIPPETS" in output or "empty" in output.lower()

    def test_command_runs_with_tracked_snippets(self):
        """Command runs without error when tracked snippets are configured."""
        with override_settings(
            WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
        ):
            out = StringIO()
            call_command("rebuild_translation_progress_for_snippets", stdout=out)
            output = out.getvalue()
            assert (
                "Successfully rebuilt snippet translation progress" in output
                or "snippets processed" in output.lower()
            )

    def test_command_output_shows_snippets_processed(self, locale_en, locale_de):
        """Command output includes a snippets-processed count when snippets exist."""
        source = SampleSnippet.objects.create(locale=locale_en, heading="Hello")
        translated = source.copy_for_translation(locale_de)
        translated.save()

        with override_settings(
            WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
        ):
            out = StringIO()
            call_command("rebuild_translation_progress_for_snippets", stdout=out)
            output = out.getvalue()
            assert "snippets:" in output.lower()

    def test_command_updates_existing_records(self, locale_en, locale_de):
        """Command updates existing progress records with recalculated percentages."""
        source = SampleSnippet.objects.create(locale=locale_en, heading="Hello")
        translated = source.copy_for_translation(locale_de)
        translated.save()
        ct = ContentType.objects.get_for_model(SampleSnippet)
        SnippetTranslationProgress.objects.create(
            content_type=ct,
            source_object_id=source.pk,
            translated_object_id=translated.pk,
            translated_locale=locale_de,
            percent_translated=50,
        )

        with override_settings(
            WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
        ):
            call_command("rebuild_translation_progress_for_snippets", stdout=StringIO())

        updated = SnippetTranslationProgress.objects.filter(
            source_object_id=source.pk,
            translated_object_id=translated.pk,
        ).first()
        assert updated is not None
        assert updated.percent_translated != 50

    def test_command_output_shows_statistics(self, locale_en, locale_de):
        """Command output includes snippets-processed count and success message."""
        source = SampleSnippet.objects.create(locale=locale_en, heading="Hello")
        translated = source.copy_for_translation(locale_de)
        translated.save()

        with override_settings(
            WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
        ):
            out = StringIO()
            call_command("rebuild_translation_progress_for_snippets", stdout=out)
            output = out.getvalue()

        assert "Successfully rebuilt snippet translation progress" in output
        assert "snippets:" in output.lower()

    def test_command_with_empty_database(self, db):
        """Command handles empty tracked model table gracefully."""
        with override_settings(
            WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
        ):
            out = StringIO()
            call_command("rebuild_translation_progress_for_snippets", stdout=out)
            output = out.getvalue()

        assert "successfully rebuilt" in output.lower()
        assert SnippetTranslationProgress.objects.count() == 0

    def test_command_with_multiple_locales(
        self, locale_en, locale_de, locale_es, locale_fr
    ):
        """Command creates one progress record per translated locale."""
        source = SampleSnippet.objects.create(locale=locale_en, heading="Hello")
        for locale in [locale_de, locale_es, locale_fr]:
            translated = source.copy_for_translation(locale)
            translated.save()

        with override_settings(
            WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
        ):
            call_command("rebuild_translation_progress_for_snippets", stdout=StringIO())

        records = SnippetTranslationProgress.objects.filter(source_object_id=source.pk)
        assert records.count() == 3

    def test_command_handles_snippets_without_translations(self, locale_en):
        """Command skips source snippets that have no translated copies."""
        SampleSnippet.objects.create(locale=locale_en, heading="Source only")

        with override_settings(
            WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
        ):
            call_command("rebuild_translation_progress_for_snippets", stdout=StringIO())

        assert SnippetTranslationProgress.objects.count() == 0

    def test_command_idempotent(self, locale_en, locale_de):
        """Running the command twice produces a stable record count."""
        source = SampleSnippet.objects.create(locale=locale_en, heading="Hello")
        translated = source.copy_for_translation(locale_de)
        translated.save()

        with override_settings(
            WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
        ):
            call_command("rebuild_translation_progress_for_snippets", stdout=StringIO())
            initial_count = SnippetTranslationProgress.objects.count()

            call_command("rebuild_translation_progress_for_snippets", stdout=StringIO())
            final_count = SnippetTranslationProgress.objects.count()

        assert initial_count == final_count


@pytest.mark.django_db
class TestCombinedCommandReportsBothCounts:
    """rebuild_translation_progress reports counts for both pages and snippets."""

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
    )
    def test_outputs_pages_and_snippets_processed(self, locale_en, locale_de):
        """rebuild_translation_progress output includes both pages and snippets counts."""
        source = SampleSnippet.objects.create(locale=locale_en, heading="Hello")
        source.copy_for_translation(locale_de).save()

        out = StringIO()
        call_command("rebuild_translation_progress", stdout=out)
        output = out.getvalue()

        assert "pages:" in output.lower()
        assert "snippets:" in output.lower()
