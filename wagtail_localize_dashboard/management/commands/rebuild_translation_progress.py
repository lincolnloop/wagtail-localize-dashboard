"""Management command to rebuild translation progress cache for pages and snippets."""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from wagtail_localize_dashboard.utils import rebuild_all_progress


class Command(BaseCommand):
    """
    Rebuild translation progress cache for pages and all tracked snippets.

    Usage:
        python manage.py rebuild_translation_progress
    """

    help = _("Rebuild translation progress cache for pages and tracked snippets")

    def handle(self, *args: any, **options: any) -> None:
        start_time = timezone.now()

        self.stdout.write("Rebuilding translation progress for pages and snippets...")
        stats = rebuild_all_progress()

        elapsed = (timezone.now() - start_time).total_seconds()

        self.stdout.write("\nResults:")
        self.stdout.write(f"  Pages processed: {stats['pages']}")
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
                self.style.SUCCESS("\nSuccessfully rebuilt translation progress!")
            )
