"""Tests for dashboard forms."""

from django.conf import settings
from django.test import override_settings
from wagtail.models import Locale

import pytest
from wagtail_localize_dashboard.forms import (
    ProgressFilterForm,
    SnippetProgressFilterForm,
)

COLUMN_FILTER_OPTIONS = [
    ("group_a", "Group A", ["de", "fr"]),
    ("group_b", "Group B", ["es"]),
]


@pytest.mark.django_db
class TestProgressFilterForm:
    """Tests for ProgressFilterForm."""

    @override_settings(WAGTAIL_LOCALIZE_DASHBOARD_COLUMN_FILTER_OPTIONS=[])
    def test_column_filter_absent_when_setting_empty(self):
        form = ProgressFilterForm()
        assert "column_filter" not in form.fields

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_COLUMN_FILTER_OPTIONS=COLUMN_FILTER_OPTIONS
    )
    def test_column_filter_present_when_setting_configured(self):
        form = ProgressFilterForm()
        assert "column_filter" in form.fields
        assert form.fields["column_filter"].choices == [
            ("", "All languages"),
            ("group_a", "Group A"),
            ("group_b", "Group B"),
        ]

    def test_column_filter_absent_when_setting_unset(self):
        """Column filter is absent when the setting is not defined at all."""
        form = ProgressFilterForm()
        assert "column_filter" not in form.fields

    def test_language_dropdowns_show_only_active_locales(self):
        """Language dropdowns only include Locale objects that exist in the database."""
        Locale.objects.get_or_create(language_code="en")
        Locale.objects.get_or_create(language_code="de")
        # "it" and "fr" are in WAGTAIL_CONTENT_LANGUAGES but have no Locale object
        form = ProgressFilterForm()
        language_codes = [
            code for code, _ in form.fields["original_language"].choices if code
        ]
        assert set(language_codes) == {"en", "de"}

    def test_language_dropdowns_exclude_unconfigured_locales(self):
        """Locales in the DB but not in WAGTAIL_CONTENT_LANGUAGES are excluded."""
        Locale.objects.get_or_create(language_code="en")
        Locale.objects.get_or_create(
            language_code="zh"
        )  # not in WAGTAIL_CONTENT_LANGUAGES
        form = ProgressFilterForm()
        language_codes = [
            code for code, _ in form.fields["original_language"].choices if code
        ]
        assert "zh" not in language_codes

    def test_exists_in_language_mirrors_original_language_choices(self):
        """exists_in_language has the same per-language options as original_language."""
        Locale.objects.get_or_create(language_code="en")
        Locale.objects.get_or_create(language_code="fr")
        form = ProgressFilterForm()
        original_codes = {
            code for code, _ in form.fields["original_language"].choices if code
        }
        exists_codes = {
            code
            for code, _ in form.fields["exists_in_language"].choices
            if code and not code.startswith("__")
        }
        assert original_codes == exists_codes


@pytest.mark.django_db
class TestSnippetProgressFilterForm:
    """Tests for SnippetProgressFilterForm."""

    def test_search_field_absent(self):
        """SnippetProgressFilterForm must not have a search field."""
        form = SnippetProgressFilterForm()
        assert "search" not in form.fields

    def test_has_required_fields(self):
        """Form exposes original_language, exists_in_language, and translation_key."""
        form = SnippetProgressFilterForm()
        assert "original_language" in form.fields
        assert "exists_in_language" in form.fields
        assert "translation_key" in form.fields

    @override_settings(WAGTAIL_LOCALIZE_DASHBOARD_COLUMN_FILTER_OPTIONS=[])
    def test_column_filter_absent_when_unconfigured(self):
        """column_filter field is absent when COLUMN_FILTER_OPTIONS is empty."""
        form = SnippetProgressFilterForm()
        assert "column_filter" not in form.fields

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_COLUMN_FILTER_OPTIONS=COLUMN_FILTER_OPTIONS
    )
    def test_column_filter_present_when_configured(self):
        """column_filter field is present with correct choices when configured."""
        form = SnippetProgressFilterForm()
        assert "column_filter" in form.fields
        assert form.fields["column_filter"].choices == [
            ("", "All languages"),
            ("group_a", "Group A"),
            ("group_b", "Group B"),
        ]

    def test_exists_in_language_choices_include_all_languages_sentinel(self):
        """exists_in_language choices include the ALL_LANGUAGES sentinel value."""
        form = SnippetProgressFilterForm()
        choice_values = [c[0] for c in form.fields["exists_in_language"].choices]
        assert "__all__" in choice_values

    def test_exists_in_language_choices_reflect_active_locales(
        self, locale_en, locale_de
    ):
        """exists_in_language includes active Locale objects, not every WAGTAIL_CONTENT_LANGUAGES entry."""
        active_codes = set(Locale.objects.values_list("language_code", flat=True))
        configured_codes = {code for code, _ in settings.WAGTAIL_CONTENT_LANGUAGES}
        inactive_codes = configured_codes - active_codes

        form = SnippetProgressFilterForm()
        choice_values = [c[0] for c in form.fields["exists_in_language"].choices]

        for code in active_codes:
            assert code in choice_values
        for code in inactive_codes:
            assert code not in choice_values

    def test_core_languages_choice_absent_when_not_configured(self):
        """CORE_LANGUAGES sentinel is absent when WAGTAIL_LOCALIZE_DASHBOARD_CORE_LANGUAGES is not defined."""
        form = SnippetProgressFilterForm()
        choice_values = [c[0] for c in form.fields["exists_in_language"].choices]
        assert "__core__" not in choice_values

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_CORE_LANGUAGES=[("de", "German"), ("fr", "French")]
    )
    def test_core_languages_choice_present_when_configured(self):
        """CORE_LANGUAGES sentinel is present when WAGTAIL_LOCALIZE_DASHBOARD_CORE_LANGUAGES is defined."""
        form = SnippetProgressFilterForm()
        choice_values = [c[0] for c in form.fields["exists_in_language"].choices]
        assert "__core__" in choice_values
