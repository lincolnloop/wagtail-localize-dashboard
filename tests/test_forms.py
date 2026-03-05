"""Tests for dashboard forms."""

from django.test import override_settings

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
