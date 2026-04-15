"""Management command to rebuild translation progress cache for pages."""

from django.core.management.base import BaseCommand, CommandParser
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from wagtail_localize_dashboard.utils import rebuild_all_progress_for_pages


class Command(BaseCommand):
    """
    Rebuild translation progress cache for pages only.

    Usage:
        python manage.py rebuild_translation_progress_for_pages
        python manage.py rebuild_translation_progress_for_pages --clean-orphans
    """

    help = _("Rebuild translation progress cache for pages")

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--clean-orphans",
            action="store_true",
            help=_("Clean up orphaned progress records first"),
        )

    def handle(self, *args: any, **options: any) -> None:
        start_time = timezone.now()

        self.stdout.write("Rebuilding translation progress for pages...")
        stats = rebuild_all_progress_for_pages()

        elapsed = (timezone.now() - start_time).total_seconds()

        self.stdout.write("\nResults:")
        self.stdout.write(f"  Pages processed: {stats['pages']}")
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
                self.style.SUCCESS("\nSuccessfully rebuilt page translation progress!")
            )
