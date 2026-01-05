"""
Management command to set up the demo site with sample data.
"""

from datetime import date
from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from wagtail.models import Locale, Page, Site

from home.models import ArticlePage, HomePage, ProductPage

User = get_user_model()


class Command(BaseCommand):
    """Set up the demo site with sample data."""

    help = "Set up the demo site with sample data"

    def handle(self, *args: Any, **options: Any) -> None:
        """Execute the command."""
        self.stdout.write("Setting up demo site...")

        # Check if we have existing demo data
        if HomePage.objects.exists():
            self.stdout.write(
                self.style.WARNING(
                    "\nDemo data already exists!\n"
                    "If you want to reset, run:\n"
                    "  rm db.sqlite3\n"
                    "  python manage.py migrate\n"
                    "  python manage.py setup_demo\n"
                )
            )
            return

        # Create superuser if it doesn't exist
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser(
                username="admin",
                email="admin@example.com",
                password="admin",
            )
            self.stdout.write(self.style.SUCCESS("Created superuser: admin/admin"))
        else:
            self.stdout.write("Superuser already exists")

        # Get or create locales
        en_locale, created = Locale.objects.get_or_create(
            language_code="en",
        )
        if created:
            self.stdout.write(self.style.SUCCESS("Created English locale"))

        de_locale, created = Locale.objects.get_or_create(
            language_code="de",
        )
        if created:
            self.stdout.write(self.style.SUCCESS("Created German locale"))

        es_locale, created = Locale.objects.get_or_create(
            language_code="es",
        )
        if created:
            self.stdout.write(self.style.SUCCESS("Created Spanish locale"))

        # Get the root page
        root_page = Page.objects.get(depth=1)

        # Delete the default Wagtail page if it exists
        home_pages = Page.objects.filter(slug="home", depth=2)
        for page in home_pages:
            if not isinstance(page.specific, HomePage):
                page.delete()
                self.stdout.write("Deleted default Wagtail home page")
                # IMPORTANT: Refresh root from database after deletion
                root_page = Page.objects.get(depth=1)
                break

        # Create home page
        home_page = HomePage(
            title="Welcome to Our Site",
            slug="home",
            tagline="Demonstrating wagtail-localize-dashboard",
            intro=(
                "<p>This is an example site showing how to use the wagtail-localize-dashboard "
                "package to track translation progress across multiple languages.</p>"
            ),
            body=[
                ("heading", "About This Demo"),
                (
                    "paragraph",
                    (
                        "<p>This demo includes several types of pages with translatable content. "
                        "You can create translations for these pages using Wagtail Localize, and "
                        "the translation dashboard will automatically track progress.</p>"
                    ),
                ),
                ("heading", "Key Features"),
                (
                    "paragraph",
                    (
                        "<p>The dashboard provides color-coded status indicators, filtering by "
                        "language, and search functionality. All translation progress is cached "
                        "for fast loading and updated automatically when translations change.</p>"
                    ),
                ),
            ],
            locale=en_locale,
        )
        root_page.add_child(instance=home_page)
        self.stdout.write(self.style.SUCCESS(f"Created home page: {home_page.title}"))

        # Update or create the default site to use our home page
        try:
            site = Site.objects.get(is_default_site=True)
            if site.root_page_id != home_page.id:
                site.root_page = home_page
                site.save()
                self.stdout.write(self.style.SUCCESS("Updated default site"))
        except Site.DoesNotExist:
            Site.objects.create(
                hostname="localhost",
                port=8000,
                root_page=home_page,
                is_default_site=True,
                site_name="wagtail-localize-dashboard Example",
            )
            self.stdout.write(self.style.SUCCESS("Created default site"))

        # Create article pages
        article1 = ArticlePage(
            title="Getting Started with Translations",
            slug="getting-started",
            date=date(2025, 1, 1),
            intro="Learn how to translate your content effectively.",
            body=(
                "<p>Wagtail Localize makes it easy to translate your content. Simply sync the "
                "source content, translate the strings, and publish. The dashboard helps you track "
                "progress across all your pages and languages.</p>"
            ),
            author="Demo Author",
            locale=en_locale,
        )
        home_page.add_child(instance=article1)
        self.stdout.write(self.style.SUCCESS(f"Created article: {article1.title}"))

        article2 = ArticlePage(
            title="Managing Multiple Languages",
            slug="multiple-languages",
            date=date(2025, 1, 15),
            intro="Best practices for multilingual content management.",
            body=(
                "<p>When managing content in multiple languages, it's important to have visibility "
                "into translation progress. The translation dashboard provides an at-a-glance view "
                "of completion status for all your pages across all languages.</p>"
            ),
            author="Demo Author",
            locale=en_locale,
        )
        home_page.add_child(instance=article2)
        self.stdout.write(self.style.SUCCESS(f"Created article: {article2.title}"))

        # Create product pages
        product1 = ProductPage(
            title="Premium Translation Package",
            slug="premium-package",
            description="<p>Our premium package includes advanced translation features, priority support, and custom integrations.</p>",
            price=Decimal("99.99"),
            sku="PKG-PREM-001",
            features=[
                (
                    "feature",
                    {
                        "title": "Advanced Features",
                        "description": "Access to all advanced translation features including machine translation and translation memory.",
                    },
                ),
                (
                    "feature",
                    {
                        "title": "Priority Support",
                        "description": "Get help when you need it with priority email and chat support.",
                    },
                ),
                (
                    "feature",
                    {
                        "title": "Custom Integrations",
                        "description": "Connect with your existing tools and workflows through our API.",
                    },
                ),
            ],
            locale=en_locale,
        )
        home_page.add_child(instance=product1)
        self.stdout.write(self.style.SUCCESS(f"Created product: {product1.title}"))

        product2 = ProductPage(
            title="Basic Translation Package",
            slug="basic-package",
            description="<p>Get started with our basic package, perfect for small sites and simple translation needs.</p>",
            price=Decimal("29.99"),
            sku="PKG-BASIC-001",
            features=[
                (
                    "feature",
                    {
                        "title": "Core Features",
                        "description": "All the essential features you need to translate your content.",
                    },
                ),
                (
                    "feature",
                    {
                        "title": "Email Support",
                        "description": "Get help via email within 24 hours.",
                    },
                ),
            ],
            locale=en_locale,
        )
        home_page.add_child(instance=product2)
        self.stdout.write(self.style.SUCCESS(f"Created product: {product2.title}"))

        self.stdout.write(
            self.style.SUCCESS(
                "\nDemo setup complete! You can now:\n"
                "1. Visit the admin at /admin/ (login: admin/admin)\n"
                "2. View the translation dashboard at /admin/translations/\n"
                "3. Create translations for the sample pages\n"
                "4. Watch the dashboard update automatically"
            )
        )
