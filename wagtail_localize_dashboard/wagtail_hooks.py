"""Wagtail hooks for adding dashboard to admin menu."""

from typing import Optional

from django.urls import reverse

from wagtail import hooks
from wagtail.admin.menu import MenuItem
from wagtail.admin.widgets import Button

from .settings import get_setting


@hooks.register("register_admin_menu_item")
def register_translation_dashboard_menu() -> Optional[MenuItem]:
    """Add translation dashboard to Wagtail admin menu."""
    if not get_setting("SHOW_IN_MENU"):
        return None

    return MenuItem(
        get_setting("MENU_LABEL"),
        reverse("wagtail_localize_dashboard:dashboard"),
        icon_name=get_setting("MENU_ICON"),
        order=get_setting("MENU_ORDER"),
    )


@hooks.register("construct_page_listing_buttons")
def add_translations_button(buttons, page, user, context=None):
    """
    Add a 'See Translations' button to pages in the explorer.

    Note: since home pages (and the root page) are not visible on the translations
    list page, we do not show a 'See Translations' link for the home pages (or
    the root page).
    """
    if page.depth > 2:  # Only show the button for descendants of home pages
        translations_button = Button(
            label="See Translations",
            url=f"{reverse('wagtail_localize_dashboard:dashboard')}?translation_key={page.translation_key}",
            classname="button",
            attrs={"target": "_blank"},
            priority=100,
        )
        buttons.append(translations_button)
    return buttons
