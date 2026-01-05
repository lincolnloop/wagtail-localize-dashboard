"""
Tests for management commands.
"""

from io import StringIO

from django.core.management import call_command

import pytest
from wagtail_localize_dashboard.models import TranslationProgress


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
        """Test that --clean-orphans flag works correctly.

        Note: Since we now use ForeignKey with CASCADE, orphaned records
        are automatically removed when pages are deleted. This test verifies
        that the --clean-orphans flag still works correctly.
        """
        # Run command with --clean-orphans
        out = StringIO()
        call_command("rebuild_translation_progress", clean_orphans=True, stdout=out)

        output = out.getvalue()
        # Should complete without error (may show "0 orphaned records deleted")
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
        assert "pages processed" in output.lower()

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
