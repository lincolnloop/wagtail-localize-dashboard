"""Tests for models in wagtail-localize-dashboard."""

from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

import pytest
from tests.models import DraftStateSnippet, SampleSnippet
from wagtail_localize_dashboard.models import (
    SnippetTranslationProgress,
    TranslationProgress,
)

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


class TestSnippetTranslationProgress:
    """Tests for the SnippetTranslationProgress model."""

    def test_str_representation(self, locale_en, locale_de):
        """__str__ includes source/translated IDs and percent."""
        source = SampleSnippet.objects.create(locale=locale_en, heading="Hello")
        translated = SampleSnippet.objects.create(locale=locale_de, heading="Hallo")
        ct = ContentType.objects.get_for_model(SampleSnippet)

        progress = SnippetTranslationProgress.objects.create(
            content_type=ct,
            source_object_id=source.pk,
            translated_object_id=translated.pk,
            translated_locale=locale_de,
            percent_translated=42,
        )

        expected_str_repr = (
            f"{progress.content_type} #{progress.source_object_id} -> "
            f"#{progress.translated_object_id} ({progress.percent_translated}%)"
        )
        assert str(progress) == expected_str_repr

    def test_get_edit_url(self, locale_en, locale_de):
        """get_edit_url returns a URL string containing the translated pk."""
        source = SampleSnippet.objects.create(locale=locale_en, heading="Hello")
        translated = SampleSnippet.objects.create(locale=locale_de, heading="Hallo")
        ct = ContentType.objects.get_for_model(SampleSnippet)

        progress = SnippetTranslationProgress.objects.create(
            content_type=ct,
            source_object_id=source.pk,
            translated_object_id=translated.pk,
            translated_locale=locale_de,
            percent_translated=0,
        )

        url = progress.get_edit_url()
        assert isinstance(url, str)
        assert str(translated.pk) in url

    def test_to_dict_without_draft_state(self, locale_en, locale_de):
        """For non-DraftStateMixin snippets, live and has_unpublished_changes are None."""
        source = SampleSnippet.objects.create(locale=locale_en, heading="Hello")
        translated = SampleSnippet.objects.create(locale=locale_de, heading="Hallo")
        ct = ContentType.objects.get_for_model(SampleSnippet)

        SnippetTranslationProgress.objects.create(
            content_type=ct,
            source_object_id=source.pk,
            translated_object_id=translated.pk,
            translated_locale=locale_de,
            percent_translated=50,
        )
        progress = (
            SnippetTranslationProgress.objects.select_related(
                "translated_locale", "content_type"
            )
            .prefetch_related("translated")
            .first()
        )

        result = progress.to_dict()

        assert result["locale"] == "de"
        assert result["percent_translated"] == 50
        assert result["live"] is None
        assert result["has_unpublished_changes"] is None

    def test_to_dict_with_draft_state(self, locale_en, locale_de):
        """For DraftStateMixin snippets, live and has_unpublished_changes are booleans."""
        source = DraftStateSnippet.objects.create(locale=locale_en, title="Source")
        translated = DraftStateSnippet.objects.create(
            locale=locale_de, title="Translated"
        )
        translated.save_revision().publish()
        translated.refresh_from_db()
        ct = ContentType.objects.get_for_model(DraftStateSnippet)

        SnippetTranslationProgress.objects.create(
            content_type=ct,
            source_object_id=source.pk,
            translated_object_id=translated.pk,
            translated_locale=locale_de,
            percent_translated=75,
        )
        progress = (
            SnippetTranslationProgress.objects.select_related(
                "translated_locale", "content_type"
            )
            .prefetch_related("translated")
            .first()
        )

        result = progress.to_dict()

        assert result["locale"] == "de"
        assert result["percent_translated"] == 75
        assert result["live"] is True
        assert result["has_unpublished_changes"] is False

    def test_unique_constraint(self, locale_en, locale_de):
        """Creating a duplicate progress record raises an IntegrityError."""
        source = SampleSnippet.objects.create(locale=locale_en, heading="Hello")
        translated = SampleSnippet.objects.create(locale=locale_de, heading="Hallo")
        ct = ContentType.objects.get_for_model(SampleSnippet)

        SnippetTranslationProgress.objects.create(
            content_type=ct,
            source_object_id=source.pk,
            translated_object_id=translated.pk,
            translated_locale=locale_de,
            percent_translated=0,
        )

        with pytest.raises(Exception):  # IntegrityError
            SnippetTranslationProgress.objects.create(
                content_type=ct,
                source_object_id=source.pk,
                translated_object_id=translated.pk,
                translated_locale=locale_de,
                percent_translated=50,
            )

    def test_translated_locale_fk_cascade(self, locale_en, locale_de):
        """Deleting a SampleSnippet and Locale cascades and removes SnippetTranslationProgress rows for that locale."""
        source = SampleSnippet.objects.create(locale=locale_en, heading="Hello")
        translated = SampleSnippet.objects.create(locale=locale_de, heading="Hallo")
        ct = ContentType.objects.get_for_model(SampleSnippet)

        SnippetTranslationProgress.objects.create(
            content_type=ct,
            source_object_id=source.pk,
            translated_object_id=translated.pk,
            translated_locale=locale_de,
            percent_translated=50,
        )
        assert SnippetTranslationProgress.objects.count() == 1

        # SampleSnippet.locale is a protected FK, so we must remove the snippet
        # that references locale_de before we can delete the locale itself.
        translated.delete()
        locale_de.delete()

        assert SnippetTranslationProgress.objects.count() == 0

    def test_get_edit_url_contains_app_label_and_model_name(self, locale_en, locale_de):
        """get_edit_url builds from content_type: the URL contains app_label, model, and pk."""
        source = SampleSnippet.objects.create(locale=locale_en, heading="Hello")
        translated = SampleSnippet.objects.create(locale=locale_de, heading="Hallo")
        ct = ContentType.objects.get_for_model(SampleSnippet)

        progress = SnippetTranslationProgress.objects.create(
            content_type=ct,
            source_object_id=source.pk,
            translated_object_id=translated.pk,
            translated_locale=locale_de,
            percent_translated=0,
        )

        url = progress.get_edit_url()

        assert isinstance(url, str)
        assert ct.app_label in url
        assert ct.model in url
        assert str(translated.pk) in url
