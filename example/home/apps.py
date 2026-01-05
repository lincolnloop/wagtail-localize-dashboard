"""
Home app configuration.
"""

from django.apps import AppConfig


class HomeConfig(AppConfig):
    """Configuration for the home app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "home"
    verbose_name = "Home"
