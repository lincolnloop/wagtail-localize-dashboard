"""
Settings for wagtail-localize-dashboard.

All settings are prefixed with WAGTAIL_LOCALIZE_DASHBOARD_
"""

from typing import Any

from django.conf import settings

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
    "MENU_LABEL": "Translations",
    "MENU_ICON": "wagtail-localize-language",
    "MENU_ORDER": 100,
    # Items per page in dashboard
    "ITEMS_PER_PAGE": 50,
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
