"""Tests for Wagtail admin hook registrations."""

import pytest
from django.test import override_settings
from django.urls import reverse

from wagtail.admin.menu import MenuItem, SubmenuMenuItem

from wagtail_localize_dashboard.wagtail_hooks import (
    add_translations_button,
    register_translation_dashboard_menu,
)

pytestmark = [pytest.mark.django_db]


class TestTranslationDashboardMenuHook:
    """Tests for the register_translation_dashboard_menu hook."""

    @override_settings(WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=[])
    def test_no_tracked_snippets_returns_plain_menu_item(self):
        """Returns a plain MenuItem when TRACKED_SNIPPETS is empty."""
        item = register_translation_dashboard_menu()
        assert isinstance(item, MenuItem)
        assert not isinstance(item, SubmenuMenuItem)

    @override_settings(WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=[])
    def test_single_menu_item_url_is_page_dashboard(self):
        """The single MenuItem URL points directly to the page dashboard."""
        item = register_translation_dashboard_menu()
        assert item.url == reverse("wagtail_localize_dashboard:dashboard")

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
    )
    def test_tracked_snippets_returns_submenu_item(self):
        """Returns a SubmenuMenuItem when TRACKED_SNIPPETS is non-empty."""
        item = register_translation_dashboard_menu()
        assert isinstance(item, SubmenuMenuItem)

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
    )
    def test_submenu_contains_pages_and_snippets_children(self):
        """The SubmenuMenuItem has exactly two child items: page dashboard and snippet dashboard."""
        item = register_translation_dashboard_menu()
        page_url = reverse("wagtail_localize_dashboard:dashboard")
        snippet_url = reverse("wagtail_localize_dashboard:snippet_dashboard")
        child_urls = [child.url for child in item.menu.registered_menu_items]
        assert page_url in child_urls
        assert snippet_url in child_urls

    @override_settings(WAGTAIL_LOCALIZE_DASHBOARD_SHOW_IN_MENU=False)
    def test_returns_none_when_show_in_menu_disabled(self):
        """Returns None when SHOW_IN_MENU is False, regardless of TRACKED_SNIPPETS."""
        item = register_translation_dashboard_menu()
        assert item is None


class TestPageListingButtonsHook:
    """Tests for the construct_page_listing_buttons hook."""

    def test_button_links_to_page_dashboard_not_snippet_dashboard(
        self, test_page, admin_user
    ):
        """The 'See Translations' button links to the page dashboard, not the snippet dashboard."""
        buttons = []
        add_translations_button(buttons, test_page, admin_user)

        assert len(buttons) == 1
        button_url = buttons[0].url
        assert reverse("wagtail_localize_dashboard:dashboard") in button_url
        assert "snippet" not in button_url
