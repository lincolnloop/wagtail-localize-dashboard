"""
Management command to generate snippet instances with translations into all locales.
"""

import sys
import time
from typing import Any

from django.core.management.base import BaseCommand

from wagtail.models import Locale
from wagtail_localize.models import Translation, TranslationSource

from home.models import NavigationMenu, SiteAlert


class Command(BaseCommand):
    """Generate NavigationMenu and SiteAlert snippets with translations for testing."""

    help = (
        "Generate snippet instances with translations for testing dashboard performance"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--snippets",
            type=int,
            default=50,
            help="Number of each snippet type to create (default: 50)",
        )
        parser.add_argument(
            "--skip-translations",
            action="store_true",
            help="Skip creating translations (only create source snippets)",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=10,
            help="Batch size for progress reporting (default: 10)",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        num_snippets = options["snippets"]
        skip_translations = options["skip_translations"]
        batch_size = options["batch_size"]

        self.stdout.write(
            self.style.WARNING(
                f"\n{'=' * 70}\nGENERATE SNIPPETS FOR LARGE-SCALE TESTING\n{'=' * 70}\n"
                f"This will create {num_snippets} NavigationMenu and {num_snippets} SiteAlert snippets in English.\n"
            )
        )

        if not skip_translations:
            num_locales = Locale.objects.exclude(language_code="en").count()
            total_snippets = num_snippets * 2 * (1 + num_locales)
            self.stdout.write(
                f"Each snippet will be translated into {num_locales} locales.\n"
                f"Total snippet instances to create: {total_snippets:,}\n"
            )

        if not self.confirm():
            self.stdout.write(self.style.ERROR("Aborted."))
            return

        try:
            default_locale = Locale.objects.get(language_code="en")
        except Locale.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(
                    "English locale not found. Please run 'python manage.py setup_locales' first."
                )
            )
            return

        if not skip_translations:
            target_locales = list(
                Locale.objects.exclude(language_code="en").order_by("language_code")
            )
            if not target_locales:
                self.stdout.write(
                    self.style.WARNING(
                        "No target locales found. Only source snippets will be created."
                    )
                )
                skip_translations = True
        else:
            target_locales = []

        # Create NavigationMenu snippets
        self.stdout.write(f"\nCreating {num_snippets} NavigationMenu snippets...")
        nav_menus = self._create_navigation_menus(
            num_snippets, default_locale, batch_size
        )
        self.stdout.write(
            self.style.SUCCESS(f"✓ Created {len(nav_menus)} NavigationMenu snippets")
        )

        # Create SiteAlert snippets
        self.stdout.write(f"\nCreating {num_snippets} SiteAlert snippets...")
        site_alerts = self._create_site_alerts(num_snippets, default_locale, batch_size)
        self.stdout.write(
            self.style.SUCCESS(f"✓ Created {len(site_alerts)} SiteAlert snippets")
        )

        all_snippets = nav_menus + site_alerts

        # Create translations
        translations_created = 0
        if not skip_translations:
            self.stdout.write(
                f"\nCreating translations into {len(target_locales)} locales..."
            )
            translations_created = self._create_translations(
                all_snippets, target_locales, batch_size
            )
            self.stdout.write(
                self.style.SUCCESS(f"✓ Created {translations_created:,} translations")
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"\n{'=' * 70}\nGENERATION COMPLETE\n{'=' * 70}\n"
                f"NavigationMenu snippets: {len(nav_menus)}\n"
                f"SiteAlert snippets: {len(site_alerts)}\n"
            )
        )
        if not skip_translations:
            self.stdout.write(f"Translations: {translations_created:,}\n")

        self.stdout.write(
            "\nNext steps:\n"
            "1. Run 'python manage.py rebuild_translation_progress_for_snippets' to build the cache\n"
            "2. Visit /admin/translations/snippets/ to view the snippet translation dashboard\n"
        )

    def confirm(self) -> bool:
        response = input("\nProceed? [y/N]: ")
        return response.lower() in ["y", "yes"]

    def _create_navigation_menus(
        self, count: int, locale: Locale, batch_size: int
    ) -> list:
        menus = []
        topics = [
            "Main Navigation",
            "Footer Links",
            "Sidebar Menu",
            "Header Menu",
            "Mobile Navigation",
            "Product Menu",
            "Help & Support",
            "Legal Links",
        ]
        for i in range(count):
            topic = topics[i % len(topics)]
            menu = NavigationMenu(
                title=f"{topic} {i + 1}",
                locale=locale,
            )
            menu.save()
            menus.append(menu)
            if (i + 1) % batch_size == 0:
                self.stdout.write(f"  Created {i + 1}/{count} navigation menus...")
        return menus

    def _create_site_alerts(self, count: int, locale: Locale, batch_size: int) -> list:
        alerts = []
        messages = [
            "This site is currently undergoing scheduled maintenance.",
            "We have updated our privacy policy. Please review the changes.",
            "New features have been released. Check out what's new.",
            "Our offices will be closed during the upcoming holiday period.",
            "Important security update: please change your password.",
            "We are experiencing intermittent issues. Our team is working on a fix.",
            "Registration is now open for our annual conference.",
            "Free shipping on all orders this weekend.",
        ]
        for i in range(count):
            message = messages[i % len(messages)]
            alert = SiteAlert(
                message=f"{message} (Alert {i + 1})",
                locale=locale,
            )
            alert.save()
            alert.save_revision().publish()
            alerts.append(alert)
            if (i + 1) % batch_size == 0:
                self.stdout.write(f"  Created {i + 1}/{count} site alerts...")
        return alerts

    def _create_translations(
        self, source_snippets: list, target_locales: list, batch_size: int
    ) -> int:
        total_translations = 0
        total_to_create = len(source_snippets) * len(target_locales)
        start_time = time.time()

        self.stdout.write(
            f"  Total to create: {len(source_snippets)} snippets × {len(target_locales)} locales "
            f"= {total_to_create:,} translations"
        )
        sys.stdout.flush()

        for idx, snippet in enumerate(source_snippets):
            try:
                translation_source, _ = TranslationSource.get_or_create_from_instance(
                    snippet
                )
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(
                        f"  Could not create translation source for {snippet}: {e}"
                    )
                )
                sys.stdout.flush()
                continue

            for locale in target_locales:
                try:
                    translation, created = Translation.objects.get_or_create(
                        source=translation_source,
                        target_locale=locale,
                    )
                    if created:
                        translation.save_target()
                        total_translations += 1
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  Could not translate {snippet} to {locale.language_code}: {e}"
                        )
                    )
                    sys.stdout.flush()
                    continue

            if (idx + 1) % batch_size == 0:
                elapsed = time.time() - start_time
                done = idx + 1
                remaining = len(source_snippets) - done
                if done > 0:
                    eta_seconds = (elapsed / done) * remaining
                    eta_str = (
                        f"{eta_seconds:.0f}s"
                        if eta_seconds < 60
                        else f"{eta_seconds / 60:.1f}m"
                    )
                    percent = (done / len(source_snippets)) * 100
                    self.stdout.write(
                        f"  [{percent:5.1f}%] Snippet {done}/{len(source_snippets)} | "
                        f"Translations: {total_translations:,}/{total_to_create:,} | "
                        f"ETA: {eta_str}"
                    )
                    sys.stdout.flush()

        total_time = time.time() - start_time
        self.stdout.write(f"\n  Translation creation completed in {total_time:.1f}s")
        sys.stdout.flush()
        return total_translations
