"""Tests for models in wagtail-localize-dashboard."""

from django.urls import reverse

import pytest
from wagtail_localize_dashboard.models import TranslationProgress

pytestmark = [pytest.mark.django_db]


class TestTranslationProgress:
    """Tests for the TranslationProgress model."""

    def test_create_translation_progress(self, test_page, locale_de):
        """Test creating a TranslationProgress instance."""
        de_page = test_page.copy_for_translation(locale_de, copy_parents=True)
        de_page.save()

        progress = TranslationProgress.objects.create(
            source_page=test_page,
            translated_page=de_page,
            percent_translated=50,
        )

        assert progress.source_page_id == test_page.id
        assert progress.translated_page_id == de_page.id
        assert progress.percent_translated == 50

    def test_to_dict(self, test_page, locale_de):
        """Test the to_dict method."""
        de_page = test_page.copy_for_translation(locale_de, copy_parents=True)
        de_page.save()

        # Create progress
        progress = TranslationProgress.objects.create(
            source_page=test_page,
            translated_page=de_page,
            percent_translated=75,
        )

        result = progress.to_dict()

        assert isinstance(result, dict)
        assert result["locale"] == "de"
        assert result["percent_translated"] == 75
        assert result["edit_url"] == reverse(
            "wagtailadmin_pages:edit", args=[de_page.id]
        )
        assert result["view_url"] == de_page.get_url()

    def test_str_representation(self, test_page, locale_de):
        """Test the __str__ method."""
        de_page = test_page.copy_for_translation(locale_de, copy_parents=True)
        de_page.save()

        # Create progress
        progress = TranslationProgress.objects.create(
            source_page=test_page,
            translated_page=de_page,
            percent_translated=50,
        )

        expected_str_repr = f"{progress.source_page} -> {progress.translated_page} ({progress.percent_translated}%)"
        assert str(progress) == expected_str_repr

    def test_unique_constraint(self, test_page, locale_de):
        """Test that the unique constraint works."""
        de_page = test_page.copy_for_translation(locale_de, copy_parents=True)
        de_page.save()

        # Create first progress record
        TranslationProgress.objects.create(
            source_page=test_page,
            translated_page=de_page,
            percent_translated=50,
        )

        # Attempting to create duplicate should fail
        with pytest.raises(Exception):  # IntegrityError
            TranslationProgress.objects.create(
                source_page=test_page,
                translated_page=de_page,
                percent_translated=75,
            )

    def test_update_or_create(self, test_page, locale_de):
        """Test that update_or_create works correctly."""
        de_page = test_page.copy_for_translation(locale_de, copy_parents=True)
        de_page.save()

        # Create initial record
        progress, created = TranslationProgress.objects.update_or_create(
            source_page=test_page,
            translated_page=de_page,
            defaults={"percent_translated": 50},
        )

        assert created is True
        assert progress.percent_translated == 50

        # Update the record
        progress, created = TranslationProgress.objects.update_or_create(
            source_page=test_page,
            translated_page=de_page,
            defaults={"percent_translated": 75},
        )

        assert created is False
        assert progress.percent_translated == 75
        assert TranslationProgress.objects.count() == 1

    def test_ordering(self, test_page, locale_de, locale_es):
        """Test that records are ordered by last_updated descending."""
        de_page = test_page.copy_for_translation(locale_de, copy_parents=True)
        de_page.save()
        es_page = test_page.copy_for_translation(locale_es, copy_parents=True)
        es_page.save()

        # Create multiple records
        progress1 = TranslationProgress.objects.create(
            source_page=test_page,
            translated_page=de_page,
            percent_translated=50,
        )

        progress2 = TranslationProgress.objects.create(
            source_page=test_page,
            translated_page=es_page,
            percent_translated=75,
        )

        # Get all records (should be ordered by last_updated desc)
        records = list(TranslationProgress.objects.all())

        # Most recent should be first
        assert records[0].id == progress2.id
        assert records[1].id == progress1.id
