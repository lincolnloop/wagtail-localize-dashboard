"""
Tests for dashboard views.
"""

from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

import pytest
from wagtail.models import Page
from wagtail_localize.models import Translation, TranslationSource
from wagtail_localize_dashboard.models import TranslationProgress


@pytest.mark.django_db
class TestDashboardView:
    """Tests for the main dashboard view."""

    def test_dashboard_requires_authentication(self, client):
        """Test that dashboard requires login."""
        url = reverse("wagtail_localize_dashboard:dashboard")
        response = client.get(url)

        # Should redirect to login
        assert response.status_code == 302
        assert response.url == f"/django-admin/login/?next={url}"

    def test_dashboard_accessible_by_admin(self, admin_client, home_page):
        """Test that admin users can access dashboard."""
        url = reverse("wagtail_localize_dashboard:dashboard")
        response = admin_client.get(url)

        assert response.status_code == 200
        assert (
            b"Translation Dashboard" in response.content
            or b"Translations" in response.content
        )

    def test_dashboard_accessible_by_staff(self, staff_client, home_page):
        """Test that staff users can access dashboard."""
        url = reverse("wagtail_localize_dashboard:dashboard")
        response = staff_client.get(url)

        assert response.status_code == 200

    def test_dashboard_shows_pages(self, admin_client, test_page):
        """Test that dashboard displays pages."""
        url = reverse("wagtail_localize_dashboard:dashboard")
        response = admin_client.get(url)

        assert response.status_code == 200
        # Response should show the test page
        assert [p["page"] for p in response.context["pages_with_progress"]] == [
            test_page
        ]
        assert test_page.title.encode() in response.content

    def test_dashboard_shows_translation_progress(
        self, admin_client, test_page_with_translations, locale_de
    ):
        """Test that dashboard shows translation progress."""
        # Create progress record
        de_translation = test_page_with_translations.get_translation(locale_de)

        TranslationProgress.objects.create(
            source_page=test_page_with_translations,
            translated_page=de_translation,
            percent_translated=75,
        )

        url = reverse("wagtail_localize_dashboard:dashboard")
        response = admin_client.get(url)

        assert response.status_code == 200
        # Response should show progress percentage
        assert b"75" in response.content or b"75%" in response.content
        assert [p["page"] for p in response.context["pages_with_progress"]] == [
            test_page_with_translations
        ]
        translations = response.context["pages_with_progress"][0]["translations"]
        assert [t_data["percent_translated"] for t_data in translations] == [75]
        assert [t_data["locale"] for t_data in translations] == ["de"]

    def test_dashboard_search_filter(self, admin_client, test_page):
        """Test search filtering on dashboard."""
        url = reverse("wagtail_localize_dashboard:dashboard")
        response = admin_client.get(url, {"search": test_page.title})

        assert response.status_code == 200
        # Response should show the test page
        assert [p["page"] for p in response.context["pages_with_progress"]] == [
            test_page
        ]

    def test_dashboard_search_no_results(self, admin_client, test_page):
        """Test search with no matching results."""
        url = reverse("wagtail_localize_dashboard:dashboard")
        response = admin_client.get(url, {"search": "NonexistentPageTitle12345"})

        assert response.status_code == 200
        # Should show no results message
        assert [p["page"] for p in response.context["pages_with_progress"]] == []

    def test_dashboard_language_filter(
        self, admin_client, test_page_with_translations, locale_en
    ):
        """Test filtering by original language."""
        url = reverse("wagtail_localize_dashboard:dashboard")

        # Searching by English should show the test_page_with_translations.
        response = admin_client.get(url, {"original_language": "en"})
        assert response.status_code == 200
        assert [p["page"] for p in response.context["pages_with_progress"]] == [
            test_page_with_translations
        ]

        # Searching by Spanish should show no results.
        response = admin_client.get(url, {"original_language": "es"})
        assert response.status_code == 200
        assert [p["page"] for p in response.context["pages_with_progress"]] == []

    def test_dashboard_translation_key_filter(
        self, admin_client, test_page_with_translations
    ):
        """Test filtering by translation key."""
        url = reverse("wagtail_localize_dashboard:dashboard")
        response = admin_client.get(
            url, {"translation_key": test_page_with_translations.translation_key}
        )

        assert response.status_code == 200
        # Response should show only pages with this translation key
        assert [p["page"] for p in response.context["pages_with_progress"]] == [
            test_page_with_translations
        ]

    def test_dashboard_pagination(self, admin_client, home_page, locale_en):
        """Test pagination on dashboard."""
        # Create multiple test pages
        page_ct = ContentType.objects.get_for_model(Page)
        for i in range(60):  # Create more than one page of results
            page = Page(
                title=f"Test Page {i}",
                slug=f"test-page-{i}",
                locale=locale_en,
                content_type=page_ct,
            )
            home_page.add_child(instance=page)

        url = reverse("wagtail_localize_dashboard:dashboard")

        # Test first page
        response = admin_client.get(url)
        assert response.status_code == 200

        # Test second page
        response = admin_client.get(url, {"page": 2})
        assert response.status_code == 200

    def test_dashboard_empty_state(self, admin_client, db):
        """Test dashboard when no pages exist."""
        # Clear all pages except root
        Page.objects.filter(depth__gt=1).delete()

        url = reverse("wagtail_localize_dashboard:dashboard")
        response = admin_client.get(url)

        assert response.status_code == 200
        # Should show empty state message
        assert [p["page"] for p in response.context["pages_with_progress"]] == []
        assert "No pages found." in response.content.decode()

    def test_dashboard_multiple_locales(
        self, admin_client, test_page, locale_de, locale_es, locale_fr
    ):
        """Test dashboard with pages in multiple locales."""
        # Patch transaction.on_commit to execute callbacks immediately, so that
        # TranslationProgress objects get created whe translations are created.
        with patch.object(transaction, "on_commit", side_effect=lambda func: func()):
            # Create translation source
            translation_source, _ = TranslationSource.get_or_create_from_instance(
                test_page
            )

            # Create translations using wagtail-localize (this creates actual translated Pages)
            for locale in [locale_de, locale_es, locale_fr]:
                translation, _ = Translation.objects.get_or_create(
                    source=translation_source,
                    target_locale=locale,
                )
                translation.save_target(publish=True)

        response = admin_client.get(reverse("wagtail_localize_dashboard:dashboard"))

        assert response.status_code == 200
        assert [p["page"] for p in response.context["pages_with_progress"]] == [
            test_page
        ]
        translations = response.context["pages_with_progress"][0]["translations"]
        assert set([t_data["locale"] for t_data in translations]) == set(
            ["de", "es", "fr"]
        )

    def test_dashboard_query_count_optimized(
        self, admin_client, home_page, locale_en, locale_de, locale_es, locale_fr
    ):
        """Test that dashboard uses optimized queries (no N+1 problem)."""

        page_ct = ContentType.objects.get_for_model(Page)

        # Create 5 pages, each with 3 translations
        num_pages = 5
        with patch.object(transaction, "on_commit", side_effect=lambda func: func()):
            for i in range(num_pages):
                # Create source page
                source_page = Page(
                    title=f"Test Page {i}",
                    slug=f"test-page-{i}",
                    locale=locale_en,
                    content_type=page_ct,
                )
                home_page.add_child(instance=source_page)

                # Create translation source
                translation_source, _ = TranslationSource.get_or_create_from_instance(
                    source_page
                )

                # Create translations in 3 locales
                for locale in [locale_de, locale_es, locale_fr]:
                    translation, _ = Translation.objects.get_or_create(
                        source=translation_source,
                        target_locale=locale,
                    )
                    translation.save_target(publish=True)

        # Now test the query count when loading the dashboard
        url = reverse("wagtail_localize_dashboard:dashboard")

        with CaptureQueriesContext(connection) as queries:
            response = admin_client.get(url)

        assert response.status_code == 200

        num_queries = len(queries)
        # We should have <= 12 queries total
        assert num_queries <= 12, (
            f"Too many queries: {num_queries}. Expected <= 12. Queries:\n"
            + "\n".join([q["sql"] for q in queries])
        )

        # Verify the pages are actually shown
        assert len(response.context["pages_with_progress"]) == num_pages

    def test_dashboard_edit_links(self, admin_client, test_page):
        """Test that dashboard includes edit links for pages."""
        url = reverse("wagtail_localize_dashboard:dashboard")
        response = admin_client.get(url)

        assert response.status_code == 200
        # Should have edit link
        edit_url = reverse("wagtailadmin_pages:edit", args=[test_page.id])
        assert edit_url.encode() in response.content

    def test_dashboard_sorting(self, admin_client, home_page, locale_en):
        """Test sorting on dashboard."""
        page_ct = ContentType.objects.get_for_model(Page)

        # Create pages with different titles
        page_a = Page(
            title="AAA Page",
            slug="aaa-page",
            locale=locale_en,
            content_type=page_ct,
        )
        home_page.add_child(instance=page_a)

        page_z = Page(
            title="ZZZ Page",
            slug="zzz-page",
            locale=locale_en,
            content_type=page_ct,
        )
        home_page.add_child(instance=page_z)

        url = reverse("wagtail_localize_dashboard:dashboard")
        response = admin_client.get(url)

        assert response.status_code == 200
        assert [p["page"] for p in response.context["pages_with_progress"]] == [
            page_a,
            page_z,
        ]
