"""Tests for utility functions in wagtail-localize-dashboard."""

from unittest.mock import Mock, patch

from django.test import override_settings

import pytest
from wagtail.models import Locale, Page
from wagtail_localize.models import Translation, TranslationSource
from wagtail_localize_dashboard.models import TranslationProgress
from wagtail_localize_dashboard.utils import (
    create_translation_progress,
    get_translation_percentages,
    rebuild_all_progress,
)

pytestmark = [pytest.mark.django_db]


@pytest.fixture
def page_with_translations(db):
    """Create a page with multiple translations."""
    # Get or create locales
    en_locale, _ = Locale.objects.get_or_create(language_code="en")
    de_locale, _ = Locale.objects.get_or_create(language_code="de")
    fr_locale, _ = Locale.objects.get_or_create(language_code="fr")

    # Get root page
    root = Page.objects.get(depth=1)

    # Create a section page at depth=2 for each locale
    en_section = Page(title="Test Section", slug="test-section", locale=en_locale)
    root.add_child(instance=en_section)

    # Create translated section pages
    de_section = en_section.copy_for_translation(de_locale)
    de_section.save()
    fr_section = en_section.copy_for_translation(fr_locale)
    fr_section.save()

    # Create English page at depth=3 (so it passes the depth__gt=2 filter)
    en_page = Page(
        title="Test Page",
        slug="test-page",
        locale=en_locale,
    )
    en_section.add_child(instance=en_page)

    # Create translations of the test page
    de_page = en_page.copy_for_translation(de_locale)
    de_page.save()
    fr_page = en_page.copy_for_translation(fr_locale)
    fr_page.save()

    return {
        "en_page": en_page,
        "de_page": de_page,
        "fr_page": fr_page,
        "en_locale": en_locale,
        "de_locale": de_locale,
        "fr_locale": fr_locale,
    }


class TestGetTranslationPercentages:
    """Tests for get_translation_percentages function."""

    def test_get_translation_percentages_with_progress(self, page_with_translations):
        """Test getting translation percentages with actual progress."""
        en_page = page_with_translations["en_page"]
        de_locale = page_with_translations["de_locale"]

        # Create translation source and translation
        translation_source, _ = TranslationSource.get_or_create_from_instance(en_page)
        Translation.objects.create(
            source=translation_source,
            target_locale=de_locale,
            enabled=True,
        )

        # Mock get_progress to return 7 out of 10 segments translated
        # Patch the Translation class method so all instances use the mock
        with patch(
            "wagtail_localize.models.Translation.get_progress", return_value=(10, 7)
        ):
            percent = get_translation_percentages(en_page, de_locale)

        assert percent == 70

    def test_get_translation_percentages_with_zero_segments(
        self, page_with_translations
    ):
        """Test that zero segments returns 100%."""
        en_page = page_with_translations["en_page"]
        de_locale = page_with_translations["de_locale"]

        # Create translation source and translation
        translation_source, _ = TranslationSource.get_or_create_from_instance(en_page)
        Translation.objects.create(
            source=translation_source,
            target_locale=de_locale,
            enabled=True,
        )

        # Mock get_progress to return 0 segments
        with patch(
            "wagtail_localize.models.Translation.get_progress", return_value=(0, 0)
        ):
            percent = get_translation_percentages(en_page, de_locale)

        assert percent == 100

    def test_get_translation_percentages_no_translation_source(
        self, page_with_translations
    ):
        """Test that missing TranslationSource returns None."""
        en_page = page_with_translations["en_page"]
        de_locale = page_with_translations["de_locale"]

        # Don't create any translation source
        percent = get_translation_percentages(en_page, de_locale)

        assert percent is None

    def test_get_translation_percentages_no_translation(self, page_with_translations):
        """Test that missing Translation returns None."""
        en_page = page_with_translations["en_page"]
        de_locale = page_with_translations["de_locale"]

        # Create translation source but no translation
        TranslationSource.get_or_create_from_instance(en_page)

        percent = get_translation_percentages(en_page, de_locale)

        assert percent is None


class TestCreateTranslationProgress:
    """Tests for create_translation_progress function."""

    def test_create_translation_progress_no_translations(self, page_with_translations):
        """Test that a page with no translations creates no progress records."""
        en_page = page_with_translations["en_page"]
        de_page = page_with_translations["de_page"]
        fr_page = page_with_translations["fr_page"]

        # Delete the translated pages to simulate no translations
        de_page.delete()
        fr_page.delete()

        # Clear any existing progress
        TranslationProgress.objects.all().delete()

        # Create progress (should create nothing since there are no translations)
        create_translation_progress(en_page)

        assert TranslationProgress.objects.count() == 0

    def test_create_translation_progress_with_translations(
        self, page_with_translations
    ):
        """Test creating progress records for a page with translations."""
        en_page = page_with_translations["en_page"]
        de_locale = page_with_translations["de_locale"]
        fr_locale = page_with_translations["fr_locale"]

        # Create translation sources and translations
        translation_source, _ = TranslationSource.get_or_create_from_instance(en_page)

        de_translation = Translation.objects.create(
            source=translation_source,
            target_locale=de_locale,
            enabled=True,
        )
        fr_translation = Translation.objects.create(
            source=translation_source,
            target_locale=fr_locale,
            enabled=True,
        )

        # Clear any existing progress
        TranslationProgress.objects.all().delete()

        # Create progress
        create_translation_progress(en_page)

        # Should have created 2 progress records (one for each translation)
        assert TranslationProgress.objects.count() == 2
        de_page = de_translation.get_target_instance()
        fr_page = fr_translation.get_target_instance()
        assert (
            TranslationProgress.objects.filter(translated_page_id=de_page.id).count()
            == 1
        )
        assert (
            TranslationProgress.objects.filter(translated_page_id=fr_page.id).count()
            == 1
        )

        # Verify ForeignKey relationships are correct
        for progress in TranslationProgress.objects.all():
            assert progress.source_page_id == en_page.id
            assert isinstance(progress.translated_page, Page)

    def test_create_translation_progress_updates_existing(self, page_with_translations):
        """Test that create_translation_progress updates existing records."""
        en_page = page_with_translations["en_page"]
        de_locale = page_with_translations["de_locale"]
        fr_page = page_with_translations["fr_page"]

        # Delete the French page so we only have one translation
        fr_page.delete()

        # Create translation
        translation_source, _ = TranslationSource.get_or_create_from_instance(en_page)
        Translation.objects.create(
            source=translation_source,
            target_locale=de_locale,
            enabled=True,
        )

        # Create initial progress
        create_translation_progress(en_page)
        assert TranslationProgress.objects.count() == 1

        initial_progress = TranslationProgress.objects.first()
        initial_id = initial_progress.id

        # Update translation progress with mocked get_progress
        with patch(
            "wagtail_localize.models.Translation.get_progress", return_value=(10, 10)
        ):
            create_translation_progress(en_page)

        # Should still have only 1 record (updated, not duplicated)
        assert TranslationProgress.objects.count() == 1
        updated_progress = TranslationProgress.objects.first()
        assert updated_progress.id == initial_id  # Same record
        assert updated_progress.percent_translated == 100  # Updated value

    def test_create_translation_progress_uses_original_page(
        self, page_with_translations
    ):
        """Test that progress is created from the original page, not translations."""
        en_page = page_with_translations["en_page"]
        de_page = page_with_translations["de_page"]
        fr_page = page_with_translations["fr_page"]

        # Clear existing progress
        TranslationProgress.objects.all().delete()

        # Call create_translation_progress on the original English page
        # This creates progress records for all its translations
        create_translation_progress(en_page)

        # Verify progress was created
        assert TranslationProgress.objects.count() == 2
        # Source should be the English page (what we passed in)
        source_ids = TranslationProgress.objects.values_list(
            "source_page_id", flat=True
        )
        assert set(source_ids) == set([en_page.id])
        # Translated should be the German page or the French page
        translated_ids = TranslationProgress.objects.values_list(
            "translated_page_id", flat=True
        )
        assert set(translated_ids) == set([de_page.id, fr_page.id])

    @override_settings(WAGTAIL_LOCALIZE_DASHBOARD_TRACK_PAGES=False)
    def test_create_translation_progress_respects_track_pages_setting(
        self, page_with_translations
    ):
        """Test that TRACK_PAGES setting is respected."""
        en_page = page_with_translations["en_page"]
        de_locale = page_with_translations["de_locale"]

        # Create translation
        translation_source, _ = TranslationSource.get_or_create_from_instance(en_page)
        Translation.objects.create(
            source=translation_source,
            target_locale=de_locale,
            enabled=True,
        )

        # Clear existing progress
        TranslationProgress.objects.all().delete()

        # Should not create progress when TRACK_PAGES=False
        create_translation_progress(en_page)

        assert TranslationProgress.objects.count() == 0

    def test_create_translation_progress_handles_translation_chain(
        self, page_with_translations
    ):
        """Test translation chain (A→B→C) where C is translated from B."""
        en_page = page_with_translations["en_page"]
        de_page = page_with_translations["de_page"]
        fr_page = page_with_translations["fr_page"]

        # Create translation source from English to German
        translation_source_en, _ = TranslationSource.get_or_create_from_instance(
            en_page
        )
        de_translation = Translation.objects.create(
            source=translation_source_en,
            target_locale=de_page.locale,
            enabled=True,
        )

        # Create translation source from German to French
        translation_source_de, _ = TranslationSource.get_or_create_from_instance(
            de_page
        )
        fr_translation = Translation.objects.create(
            source=translation_source_de,
            target_locale=fr_page.locale,
            enabled=True,
        )

        # Clear existing progress
        TranslationProgress.objects.all().delete()

        # Create progress from English page
        create_translation_progress(en_page)

        # Should create progress for both German and French
        assert TranslationProgress.objects.count() == 2
        de_page = de_translation.get_target_instance()
        fr_page = fr_translation.get_target_instance()
        assert (
            TranslationProgress.objects.filter(translated_page_id=de_page.id).count()
            == 1
        )
        assert (
            TranslationProgress.objects.filter(translated_page_id=fr_page.id).count()
            == 1
        )

        # All progress should reference the original English page
        for progress in TranslationProgress.objects.all():
            assert progress.source_page_id == en_page.id

    @patch(
        "wagtail_localize_dashboard.utils.TranslationSource.objects.get_for_instance"
    )
    @patch("wagtail_localize_dashboard.utils.Translation.objects.get")
    def test_create_translation_progress_fallback_to_nested_search(
        self, mock_translation_get, mock_translation_source_get, page_with_translations
    ):
        """Test the fallback logic when translation is from another translation."""
        mock_translation_record = Mock()
        mock_translation_record.get_progress.return_value = (8, 6)  # 75% translated

        mock_translation_source_get.side_effect = [
            TranslationSource.DoesNotExist(),
            Mock(),
            TranslationSource.DoesNotExist(),
            Mock(),
        ]
        mock_translation_get.side_effect = [
            Translation.DoesNotExist(),  # First call (direct translation) should fail
            mock_translation_record,  # Second call (translation of a translation) should succeed
        ]

        en_homepage = page_with_translations["en_page"]

        # Make sure there are currently no TranslationProgress objects.
        TranslationProgress.objects.all().delete()

        create_translation_progress(en_homepage)

        # Should find translations via the fallback method
        assert TranslationProgress.objects.count() == 2
        # At least one translation should have 75% progress from the nested search
        progress_values = {
            td.percent_translated for td in TranslationProgress.objects.all()
        }
        assert 75 in progress_values

    def test_create_translation_progress_handles_value_error(
        self, page_with_translations
    ):
        """Test create_translation_progress handles ValueError gracefully."""
        en_page = page_with_translations["en_page"]

        # Make sure there are currently no TranslationProgress objects.
        TranslationProgress.objects.all().delete()

        # Mock get_translations to raise ValueError
        with patch.object(
            Page, "get_translations", side_effect=ValueError("Test error")
        ):
            create_translation_progress(en_page)

            # Should not create any TranslationProgress when ValueError occurs
            assert TranslationProgress.objects.count() == 0

    @patch("wagtail_localize_dashboard.utils.logger")
    def test_create_translation_progress_handles_attribute_error(
        self, mock_logger, page_with_translations
    ):
        """Test create_translation_progress handles AttributeError gracefully."""
        en_homepage = page_with_translations["en_page"]

        # Make sure there are currently no TranslationProgress objects.
        TranslationProgress.objects.all().delete()

        # Mock specific property to raise AttributeError
        with patch.object(
            Page, "get_translations", side_effect=AttributeError("Test error")
        ):
            create_translation_progress(en_homepage)

            # If an AttributeError occurs, then no TranslationProgress should be created.
            assert TranslationProgress.objects.count() == 0
            # The logger was called with an exception.
            assert mock_logger.exception.call_count == 1
            # Check that the logger was called with a message containing the error
            log_message = str(mock_logger.exception.call_args_list[0].args[0])
            assert "Test error" in log_message
            assert "Error creating translation progress" in log_message


class TestRebuildAllProgress:
    """Tests for rebuild_all_progress function."""

    def test_rebuild_all_progress_empty_database(self):
        """Test rebuild_all_progress with no pages."""
        # Clear everything
        TranslationProgress.objects.all().delete()

        stats = rebuild_all_progress()

        assert stats["pages"] >= 0
        assert stats["errors"] == 0

    def test_rebuild_all_progress_with_pages(self, page_with_translations):
        """Test rebuild_all_progress creates progress for all pages."""
        en_page = page_with_translations["en_page"]
        de_locale = page_with_translations["de_locale"]

        # Create translation
        translation_source, _ = TranslationSource.get_or_create_from_instance(en_page)
        Translation.objects.create(
            source=translation_source,
            target_locale=de_locale,
            enabled=True,
        )

        # Clear existing progress
        TranslationProgress.objects.all().delete()

        # Rebuild
        stats = rebuild_all_progress()

        # Should have processed the page
        assert stats["pages"] >= 1
        assert stats["errors"] == 0

        # Should have created progress
        assert TranslationProgress.objects.count() >= 1
