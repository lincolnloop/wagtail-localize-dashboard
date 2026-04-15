"""Django app configuration for wagtail-localize-dashboard."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class DashboardConfig(AppConfig):
    """App configuration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "wagtail_localize_dashboard"
    verbose_name = _("Wagtail Localize Dashboard")

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

        # Connect snippet handlers to each tracked model individually so they
        # only fire for configured models, not as global post_save catch-alls.
        from django.db.models.signals import post_save, pre_delete

        from .settings import get_tracked_snippet_models
        from .signals import snippet_deleted_handler, snippet_saved_handler

        for model in get_tracked_snippet_models():
            post_save.connect(snippet_saved_handler, sender=model)
            pre_delete.connect(snippet_deleted_handler, sender=model)

        # Import wagtail hooks (registers menu items)
        from . import wagtail_hooks  # noqa
