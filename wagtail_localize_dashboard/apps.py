"""Django app configuration for wagtail-localize-dashboard."""

from django.apps import AppConfig


class DashboardConfig(AppConfig):
    """App configuration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "wagtail_localize_dashboard"
    verbose_name = "Wagtail Localize Dashboard"

    def ready(self) -> None:
        """
        Called when Django starts.

        - Check wagtail-localize is installed
        - Import signal handlers
        - Import wagtail hooks
        """
        # Check dependencies
        try:
            import wagtail_localize  # noqa
        except ImportError:
            raise ImportError(
                "wagtail-localize must be installed to use wagtail-localize-dashboard. Install it with: pip install wagtail-localize"
            )

        # Import signal handlers (registers them)
        from . import signals  # noqa

        # Import wagtail hooks (registers menu items)
        from . import wagtail_hooks  # noqa
