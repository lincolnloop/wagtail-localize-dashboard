"""Wagtail hooks for adding dashboard to admin menu."""

from django.urls import URLResolver, include, path, reverse
from django.utils.translation import gettext_lazy as _
from wagtail import hooks
from wagtail.admin.menu import Menu, MenuItem, SubmenuMenuItem
from wagtail.admin.widgets import Button
from wagtail_localize.models import Translation

from .settings import get_setting, get_tracked_snippet_models
from .views.management import (
    PublishTranslationBulkAction,
    UnpublishTranslationBulkAction,
)


@hooks.register("register_admin_urls")
def register_dashboard_urls() -> list[URLResolver]:
    return [path("translations/", include("wagtail_localize_dashboard.urls"))]


@hooks.register("register_admin_menu_item")
def register_translation_dashboard_menu() -> MenuItem | None:
    """
    Add translation dashboard to Wagtail admin menu.

    When TRACKED_SNIPPETS is non-empty, renders as a submenu with separate
    "Pages" and "Snippets" items. When empty (the default), renders as a
    single menu item pointing directly to the page dashboard — no behaviour
    change for users who have not configured snippet tracking.
    """
    if not get_setting("SHOW_IN_MENU"):
        return None

    icon_name = get_setting("MENU_ICON")
    order = get_setting("MENU_ORDER")
    label = get_setting("MENU_LABEL")

    if get_tracked_snippet_models():
        return SubmenuMenuItem(
            label,
            Menu(
                items=[
                    MenuItem(
                        _("Pages"),
                        reverse("wagtail_localize_dashboard:dashboard"),
                        icon_name="doc-empty-inverse",
                        order=100,
                    ),
                    MenuItem(
                        _("Snippets"),
                        reverse("wagtail_localize_dashboard:snippet_dashboard"),
                        icon_name="snippet",
                        order=200,
                    ),
                ]
            ),
            icon_name=icon_name,
            order=order,
        )

    return MenuItem(
        label,
        reverse("wagtail_localize_dashboard:dashboard"),
        icon_name=icon_name,
        order=order,
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
        if Translation.objects.filter(source__object_id=page.translation_key).exists():
            url = reverse(
                "wagtail_localize_dashboard:manage_translations", args=[page.pk]
            )
        else:
            # The manage view 404s without translations.
            url = f"{reverse('wagtail_localize_dashboard:dashboard')}?translation_key={page.translation_key}"
        translations_button = Button(
            label=_("See Translations"),
            url=url,
            classname="button button-small button-secondary",
            attrs={"target": "_blank"},
            priority=100,
        )
        buttons.append(translations_button)
    return buttons


hooks.register("register_bulk_action", PublishTranslationBulkAction)
hooks.register("register_bulk_action", UnpublishTranslationBulkAction)
