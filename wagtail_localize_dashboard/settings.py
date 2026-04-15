"""
Settings for wagtail-localize-dashboard.

All settings are prefixed with WAGTAIL_LOCALIZE_DASHBOARD_
"""

from typing import Any, List, Type

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.utils.translation import gettext_lazy as _

from wagtail_localize.models import TranslatableMixin

# Default settings
DEFAULTS = {
    # Enable/disable the entire feature
    "ENABLED": True,
    # Enable automatic cache updates via signals
    "AUTO_UPDATE": True,
    # Track translation progress for Pages
    "TRACK_PAGES": True,
    # Show dashboard in Wagtail admin menu
    "SHOW_IN_MENU": True,
    # Menu item configuration
    "MENU_LABEL": _("Translations"),
    "MENU_ICON": "wagtail-localize-language",
    "MENU_ORDER": 100,
    # Items per page in dashboard
    "ITEMS_PER_PAGE": 50,
    # Column filter options: list of (id, label, locale_codes) tuples
    "COLUMN_FILTER_OPTIONS": [],
    # Snippet models to track, e.g. ["myapp.NavigationMenu"]
    "TRACKED_SNIPPETS": [],
}


def get_setting(name: str, default: Any = None) -> Any:
    """
    Get a setting value.

    Args:
        name: Setting name (without prefix)
        default: Default value if not found

    Returns:
        Setting value from Django settings, or default

    Example:
        >>> get_setting("ENABLED")
        True
    """
    setting_name = f"WAGTAIL_LOCALIZE_DASHBOARD_{name}"
    return getattr(settings, setting_name, DEFAULTS.get(name, default))


def get_tracked_snippet_models() -> List[Type[models.Model]]:
    """
    Resolve the TRACKED_SNIPPETS setting to a list of model classes.

    Each entry must be an "app_label.ModelName" string for a model that is a
    subclass of TranslatableMixin. Raises ImproperlyConfigured on the first
    invalid entry so the developer sees a clear error at startup rather than a
    cryptic AttributeError at signal time.

    Returns:
        List of model classes (may be empty if TRACKED_SNIPPETS is not set).
    """
    tracked: List[str] = get_setting("TRACKED_SNIPPETS", [])
    result = []
    for entry in tracked:
        try:
            model = apps.get_model(entry)
        except (LookupError, ValueError):
            raise ImproperlyConfigured(
                f"WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS contains "
                f"'{entry}', which could not be resolved to a model. "
                f"Use the 'app_label.ModelName' format."
            )
        if not issubclass(model, TranslatableMixin):
            raise ImproperlyConfigured(
                f"WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS contains "
                f"'{entry}', but {model.__name__} is not a subclass of "
                f"TranslatableMixin. Only translatable models can be tracked."
            )
        result.append(model)
    return result
