"""Tests for dashboard forms."""

from django.test import override_settings
from wagtail.models import Locale

import pytest
from wagtail_localize_dashboard.forms import ProgressFilterForm

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
