"""
Management command to create all 40 locales in the database.
"""

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand

from wagtail.models import Locale


class Command(BaseCommand):
    """Create all configured locales in the database."""

    help = "Create all locales configured in WAGTAIL_CONTENT_LANGUAGES"

    def handle(self, *args: Any, **options: Any) -> None:
        """Execute the command."""
        self.stdout.write("Setting up locales...")

        created_count = 0
        existing_count = 0

        for language_code, language_name in settings.WAGTAIL_CONTENT_LANGUAGES:
            locale, created = Locale.objects.get_or_create(
                language_code=language_code,
            )

            if created:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ Created locale: {language_code} ({language_name})"
                    )
                )
                created_count += 1
            else:
                self.stdout.write(
                    f"  Locale already exists: {language_code} ({language_name})"
                )
                existing_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nLocale setup complete!\n"
                f"  Created: {created_count}\n"
                f"  Already existed: {existing_count}\n"
                f"  Total: {created_count + existing_count}"
            )
        )
