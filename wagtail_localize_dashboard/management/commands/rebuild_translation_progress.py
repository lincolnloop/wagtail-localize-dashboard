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

        self.stdout.write(
            _("Rebuilding translation progress for pages and snippets...")
        )
        stats = rebuild_all_progress()

        elapsed = (timezone.now() - start_time).total_seconds()

        self.stdout.write("")
        self.stdout.write(_("Results:"))
        self.stdout.write(_("  Pages: %(pages)d") % {"pages": stats["pages"]})
        self.stdout.write(
            _("  Snippets: %(snippets)d") % {"snippets": stats["snippets"]}
        )
        self.stdout.write(_("  Errors: %(errors)d") % {"errors": stats["errors"]})
        self.stdout.write(_("  Time: %(elapsed)s") % {"elapsed": f"{elapsed:.2f}s"})

        self.stdout.write("")
        if stats["errors"] > 0:
            self.stdout.write(self.style.WARNING(_("Completed")))
            self.stdout.write(
                self.style.WARNING(
                    _("Errors: %(errors)d.") % {"errors": stats["errors"]}
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(_("Successfully rebuilt translation progress!"))
            )
