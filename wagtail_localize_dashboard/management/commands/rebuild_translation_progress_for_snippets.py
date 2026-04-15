"""Management command to rebuild translation progress cache for snippets."""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from wagtail_localize_dashboard.settings import get_tracked_snippet_models
from wagtail_localize_dashboard.utils import rebuild_all_snippet_progress


class Command(BaseCommand):
    """
    Rebuild translation progress cache for tracked snippets only.

    Usage:
        python manage.py rebuild_translation_progress_for_snippets
    """

    help = _("Rebuild translation progress cache for tracked snippets")

    def handle(self, *args: any, **options: any) -> None:
        if not get_tracked_snippet_models():
            self.stdout.write(
                self.style.WARNING(
                    "WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS is empty. "
                    "No snippet progress to rebuild. "
                    "Add snippet models to that setting to enable snippet tracking."
                )
            )
            return

        start_time = timezone.now()

        self.stdout.write("Rebuilding translation progress for snippets...")
        stats = rebuild_all_snippet_progress()

        elapsed = (timezone.now() - start_time).total_seconds()

        self.stdout.write("\nResults:")
        self.stdout.write(f"  Snippets processed: {stats['snippets']}")
        self.stdout.write(f"  Errors: {stats['errors']}")
        self.stdout.write(f"  Time elapsed: {elapsed:.2f}s")

        if stats["errors"] > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"\nCompleted with {stats['errors']} errors. Check logs for details."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "\nSuccessfully rebuilt snippet translation progress!"
                )
            )
