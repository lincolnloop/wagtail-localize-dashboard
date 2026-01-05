"""Management command to rebuild translation progress cache."""

from django.core.management.base import BaseCommand, CommandParser
from django.utils import timezone

from wagtail_localize_dashboard.utils import rebuild_all_progress


class Command(BaseCommand):
    """
    Rebuild translation progress cache for all objects.

    Usage:
        python manage.py rebuild_translation_progress
        python manage.py rebuild_translation_progress --clean-orphans
    """

    help = "Rebuild translation progress cache for all translatable objects"

    def add_arguments(self, parser: CommandParser) -> None:
        """Add command arguments."""
        parser.add_argument(
            "--clean-orphans",
            action="store_true",
            help="Clean up orphaned progress records first",
        )

    def handle(self, *args: any, **options: any) -> None:
        """Execute the command."""
        start_time = timezone.now()

        self.stdout.write("Starting translation progress rebuild...")

        # Rebuild progress
        self.stdout.write("Rebuilding progress cache...")
        stats = rebuild_all_progress()

        # Report results
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
                self.style.SUCCESS("\nSuccessfully rebuilt translation progress!")
            )
