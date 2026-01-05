"""
Management command to generate 1000 pages with translations into all locales.
"""

import random
import sys
import time
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from wagtail.models import Locale, Page
from wagtail_localize.models import Translation, TranslationSource

from home.models import ArticlePage, ProductPage


class Command(BaseCommand):
    """Generate 1000 pages with translations into all configured locales."""

    help = "Generate 1000 pages with translations for testing dashboard performance"

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            "--pages",
            type=int,
            default=1000,
            help="Number of pages to create (default: 1000)",
        )
        parser.add_argument(
            "--skip-translations",
            action="store_true",
            help="Skip creating translations (only create source pages)",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=50,
            help="Batch size for progress reporting (default: 50)",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Execute the command."""
        num_pages = options["pages"]
        skip_translations = options["skip_translations"]
        batch_size = options["batch_size"]

        self.stdout.write(
            self.style.WARNING(
                f"\n{'=' * 70}\nGENERATE PAGES FOR LARGE-SCALE TESTING\n{'=' * 70}\nThis will create {num_pages} pages in English.\n"
            )
        )

        if not skip_translations:
            num_locales = len(settings.WAGTAIL_CONTENT_LANGUAGES) - 1  # Exclude English
            total_pages = num_pages * (1 + num_locales)
            self.stdout.write(
                f"Each page will be translated into {num_locales} locales.\nTotal pages to create: {total_pages:,}\n"
            )

        if not self.confirm():
            self.stdout.write(self.style.ERROR("Aborted."))
            return

        # Get default locale (English)
        try:
            default_locale = Locale.objects.get(language_code="en")
        except Locale.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(
                    "English locale not found. Please run 'python manage.py setup_locales' first."
                )
            )
            return

        # Get all other locales for translations
        if not skip_translations:
            target_locales = list(
                Locale.objects.exclude(language_code="en").order_by("language_code")
            )
            if not target_locales:
                self.stdout.write(
                    self.style.WARNING(
                        "No target locales found. Only source pages will be created."
                    )
                )
                skip_translations = True

        # Get the home page to add children to
        try:
            home_page = Page.objects.get(slug="home", depth=2, locale=default_locale)
        except Page.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(
                    "Home page not found. Please run 'python manage.py setup_demo' first."
                )
            )
            return

        self.stdout.write(f"\nCreating {num_pages} source pages...")

        # Generate pages
        created_pages = []
        for i in range(num_pages):
            # Alternate between ArticlePage and ProductPage
            if i % 2 == 0:
                page = self.create_article_page(i, default_locale, home_page)
            else:
                page = self.create_product_page(i, default_locale, home_page)

            created_pages.append(page)

            # Progress reporting
            if (i + 1) % batch_size == 0:
                self.stdout.write(f"  Created {i + 1}/{num_pages} pages...")

        self.stdout.write(
            self.style.SUCCESS(f"✓ Created {len(created_pages)} source pages")
        )

        # Create translations
        if not skip_translations:
            self.stdout.write(
                f"\nCreating translations into {len(target_locales)} locales..."
            )
            translations_created = self.create_translations(
                created_pages, target_locales, batch_size
            )
            self.stdout.write(
                self.style.SUCCESS(f"✓ Created {translations_created:,} translations")
            )

        # Summary
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{'=' * 70}\nGENERATION COMPLETE\n{'=' * 70}\nSource pages: {len(created_pages)}\n"
            )
        )

        if not skip_translations:
            self.stdout.write(
                f"Translations: {translations_created:,}\nTotal pages: {len(created_pages) + translations_created:,}\n"
            )

        self.stdout.write(
            "\nNext steps:\n"
            "1. Visit /admin/translations/ to view the translation dashboard\n"
            "2. Run 'python manage.py rebuild_translation_progress' to build the cache\n"
        )

    def confirm(self) -> bool:
        """Ask for user confirmation."""
        response = input("\nProceed? [y/N]: ")
        return response.lower() in ["y", "yes"]

    def create_article_page(
        self, index: int, locale: Locale, parent: Page
    ) -> ArticlePage:
        """Create an article page."""
        # Generate varied content
        topics = [
            "Translation Management",
            "Localization Best Practices",
            "Multilingual Content",
            "Global Communication",
            "Language Technology",
            "Cultural Adaptation",
            "Content Internationalization",
            "Translation Workflow",
        ]
        topic = random.choice(topics)

        # Random date within the last 2 years
        days_ago = random.randint(0, 730)
        post_date = date.today() - timedelta(days=days_ago)

        page = ArticlePage(
            title=f"{topic} - Article {index + 1}",
            slug=f"article-{index + 1}",
            date=post_date,
            intro=f"This is article number {index + 1} about {topic.lower()}. Generated for testing the translation dashboard with large datasets.",
            body=f"<p>This is the main content of article {index + 1}. "
            f"In a real scenario, this would contain substantial text content "
            f"that needs to be translated into multiple languages.</p>"
            f"<p>Topics covered: {topic}, translation management, "
            f"and multilingual content strategies.</p>",
            author=f"Author {random.randint(1, 10)}",
            locale=locale,
        )

        with transaction.atomic():
            parent.add_child(instance=page)
            # Publish the page
            revision = page.save_revision()
            revision.publish()

        return page

    def create_product_page(
        self, index: int, locale: Locale, parent: Page
    ) -> ProductPage:
        """Create a product page."""
        categories = [
            "Translation Software",
            "Localization Tools",
            "Language Services",
            "Content Management",
            "Translation Memory",
            "Machine Translation",
            "Quality Assurance",
            "Terminology Management",
        ]
        category = random.choice(categories)

        # Random price between 9.99 and 999.99
        price = Decimal(str(round(random.uniform(9.99, 999.99), 2)))

        page = ProductPage(
            title=f"{category} Product {index + 1}",
            slug=f"product-{index + 1}",
            description=f"<p>This is product {index + 1} in the {category} category. "
            f"Generated for testing translation dashboard performance with large datasets.</p>"
            f"<p>This product helps teams manage translations efficiently.</p>",
            price=price,
            sku=f"PRD-{index + 1:04d}",
            features=[
                (
                    "feature",
                    {
                        "title": "Feature 1",
                        "description": f"Primary feature of {category.lower()} product.",
                    },
                ),
                (
                    "feature",
                    {
                        "title": "Feature 2",
                        "description": "Advanced capabilities for professional users.",
                    },
                ),
            ],
            locale=locale,
        )

        with transaction.atomic():
            parent.add_child(instance=page)
            # Publish the page
            revision = page.save_revision()
            revision.publish()

        return page

    def create_translations(
        self, source_pages: list, target_locales: list, batch_size: int
    ) -> int:
        """
        Create translations for all source pages into all target locales.

        This creates Translation records in wagtail-localize, which will
        create the translated page instances.
        """
        total_translations = 0
        total_to_create = len(source_pages) * len(target_locales)
        start_time = time.time()

        self.stdout.write(
            f"  Total to create: {len(source_pages)} pages × {len(target_locales)} locales = {total_to_create:,} translations"
        )
        self.stdout.write("  Progress updates every 5 pages...\n")
        sys.stdout.flush()

        for page_idx, source_page in enumerate(source_pages):
            page_start_time = time.time()

            # Create translation source
            try:
                translation_source, created = (
                    TranslationSource.get_or_create_from_instance(source_page)
                )
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(
                        f"  Could not create translation source for {source_page}: {e}"
                    )
                )
                sys.stdout.flush()
                continue

            # Create translations for each target locale
            translations_for_page = 0
            for locale in target_locales:
                try:
                    # Check if translation already exists
                    translation, created = Translation.objects.get_or_create(
                        source=translation_source,
                        target_locale=locale,
                    )

                    if created:
                        # Create the translated page instance
                        translation.save_target(publish=True)
                        total_translations += 1
                        translations_for_page += 1

                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  Could not create translation for {source_page} to {locale.language_code}: {e}"
                        )
                    )
                    sys.stdout.flush()
                    continue

            # Progress reporting - every 5 pages
            if (page_idx + 1) % 5 == 0:
                elapsed = time.time() - start_time
                pages_done = page_idx + 1
                pages_remaining = len(source_pages) - pages_done

                # Calculate rate and ETA
                if pages_done > 0:
                    rate = elapsed / pages_done
                    eta_seconds = rate * pages_remaining
                    eta_minutes = eta_seconds / 60

                    # Format ETA
                    if eta_minutes < 1:
                        eta_str = f"{eta_seconds:.0f}s"
                    elif eta_minutes < 60:
                        eta_str = f"{eta_minutes:.1f}m"
                    else:
                        eta_hours = eta_minutes / 60
                        eta_str = f"{eta_hours:.1f}h"

                    percent = (pages_done / len(source_pages)) * 100

                    self.stdout.write(
                        f"  [{percent:5.1f}%] Page {pages_done}/{len(source_pages)} | "
                        f"Translations: {total_translations:,}/{total_to_create:,} | "
                        f"ETA: {eta_str}"
                    )
                    sys.stdout.flush()

            # Also show progress every 1 page for the first 10 pages
            elif page_idx < 10:
                page_time = time.time() - page_start_time
                self.stdout.write(
                    f"  Page {page_idx + 1}/{len(source_pages)} complete ({translations_for_page} translations, {page_time:.1f}s)"
                )
                sys.stdout.flush()

        # Final summary
        total_time = time.time() - start_time
        self.stdout.write(
            f"\n  Translation creation completed in {total_time / 60:.1f} minutes"
        )
        sys.stdout.flush()

        return total_translations
