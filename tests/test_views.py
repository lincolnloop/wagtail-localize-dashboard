"""
Tests for dashboard views.
"""

from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType
from django.db import connection, transaction
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

import pytest
from wagtail.models import Page
from wagtail_localize.models import Translation, TranslationSource
from wagtail_localize_dashboard.models import TranslationProgress
from wagtail.models import Locale

COLUMN_FILTER_OPTIONS = [
    ("group_a", "Group A", ["de", "fr"]),
    ("group_b", "Group B", ["es"]),
]


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

    @override_settings(WAGTAIL_LOCALIZE_DASHBOARD_COLUMN_FILTER_OPTIONS=[])
    def test_column_filter_absent_when_setting_empty(self, admin_client, test_page):
        """Column filter field is absent when COLUMN_FILTER_OPTIONS is empty."""
        url = reverse("wagtail_localize_dashboard:dashboard")
        response = admin_client.get(url)
        assert "column_filter" not in response.context["filter_form"].fields

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_COLUMN_FILTER_OPTIONS=COLUMN_FILTER_OPTIONS
    )
    def test_column_filter_present_when_setting_configured(
        self, admin_client, test_page
    ):
        """Column filter field is present with correct choices when configured."""
        url = reverse("wagtail_localize_dashboard:dashboard")
        response = admin_client.get(url)
        form = response.context["filter_form"]
        assert "column_filter" in form.fields
        choices = form.fields["column_filter"].choices
        assert choices == [
            ("", "All languages"),
            ("group_a", "Group A"),
            ("group_b", "Group B"),
        ]

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_COLUMN_FILTER_OPTIONS=COLUMN_FILTER_OPTIONS
    )
    def test_column_filter_no_selection_shows_all(
        self, admin_client, test_page_with_translations, locale_de
    ):
        """With no column filter selected, all translations are shown."""
        TranslationProgress.objects.create(
            source_page=test_page_with_translations,
            translated_page=test_page_with_translations.get_translation(locale_de),
            percent_translated=50,
        )
        url = reverse("wagtail_localize_dashboard:dashboard")
        response = admin_client.get(url, {"column_filter": ""})
        assert (
            len(response.context["pages_with_progress"]) == 1
        )  # Only 1 page in results
        translations = response.context["pages_with_progress"][0]["translations"]
        assert len(translations) == 1
        assert translations[0]["locale"] == "de"

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_COLUMN_FILTER_OPTIONS=COLUMN_FILTER_OPTIONS
    )
    def test_column_filter_shows_only_matching_locales(
        self, admin_client, test_page, locale_de, locale_es, locale_fr
    ):
        """Selecting a column filter shows only matching locale buttons."""
        with patch.object(transaction, "on_commit", side_effect=lambda func: func()):
            translation_source, _ = TranslationSource.get_or_create_from_instance(
                test_page
            )
            for locale in [locale_de, locale_es, locale_fr]:
                t, _ = Translation.objects.get_or_create(
                    source=translation_source, target_locale=locale
                )
                t.save_target(publish=True)

        url = reverse("wagtail_localize_dashboard:dashboard")
        # group_a includes de and fr
        response = admin_client.get(url, {"column_filter": "group_a"})
        assert (
            len(response.context["pages_with_progress"]) == 1
        )  # Only 1 page in results
        translations = response.context["pages_with_progress"][0]["translations"]
        locales = {t["locale"] for t in translations}
        assert locales == {"de", "fr"}

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_COLUMN_FILTER_OPTIONS=COLUMN_FILTER_OPTIONS
    )
    def test_column_filter_rows_with_no_matches_still_appear(
        self, admin_client, test_page_with_translations, locale_de
    ):
        """Rows with no matching translations still appear (not hidden)."""
        # test_page_with_translations has de and es translations
        # Create progress only for de
        TranslationProgress.objects.create(
            source_page=test_page_with_translations,
            translated_page=test_page_with_translations.get_translation(locale_de),
            percent_translated=100,
        )
        url = reverse("wagtail_localize_dashboard:dashboard")
        # group_b only includes es, and there's no progress record for es
        response = admin_client.get(url, {"column_filter": "group_b"})
        pages = response.context["pages_with_progress"]
        assert len(pages) == 1
        assert pages[0]["page"] == test_page_with_translations
        assert pages[0]["translations"] == []

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_COLUMN_FILTER_OPTIONS=COLUMN_FILTER_OPTIONS
    )
    def test_column_filter_shows_active_message(self, admin_client, test_page):
        """Active column filter displays a message with the chosen group label."""
        url = reverse("wagtail_localize_dashboard:dashboard")
        response = admin_client.get(url, {"column_filter": "group_a"})
        assert response.context["column_filter_label"] == "Group A"
        content = response.content.decode()
        assert "Only showing" in content
        assert "Group A" in content

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_COLUMN_FILTER_OPTIONS=COLUMN_FILTER_OPTIONS
    )
    def test_column_filter_no_message_when_unset(self, admin_client, test_page):
        """No active filter message when column filter is not selected."""
        url = reverse("wagtail_localize_dashboard:dashboard")
        response = admin_client.get(url)
        assert response.context["column_filter_label"] == ""
        assert b"Only showing" not in response.content

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_COLUMN_FILTER_OPTIONS=COLUMN_FILTER_OPTIONS
    )
    def test_column_filter_preserves_row_filters(
        self, admin_client, test_page_with_translations
    ):
        """Row filter params work alongside column filter."""
        url = reverse("wagtail_localize_dashboard:dashboard")
        response = admin_client.get(
            url,
            {
                "search": test_page_with_translations.title,
                "column_filter": "group_a",
            },
        )
        assert response.status_code == 200
        pages = response.context["pages_with_progress"]
        assert len(pages) == 1
        assert pages[0]["page"] == test_page_with_translations

    def test_exists_in_all_languages_uses_active_locales(
        self, admin_client, test_page, locale_en, locale_de, locale_es
    ):
        """'All languages' filter matches pages in all active Locale objects, not all configured languages."""
        # en, de, es are the only active locales — it and fr exist in WAGTAIL_CONTENT_LANGUAGES
        # but have no Locale objects. A page translated into en+de+es should match __all__.
        with patch.object(transaction, "on_commit", side_effect=lambda func: func()):
            source, _ = TranslationSource.get_or_create_from_instance(test_page)
            for locale in [locale_de, locale_es]:
                t, _ = Translation.objects.get_or_create(
                    source=source, target_locale=locale
                )
                t.save_target(publish=True)

        url = reverse("wagtail_localize_dashboard:dashboard")

        response = admin_client.get(url, {"exists_in_language": "__all__"})
        assert response.status_code == 200
        pages = [p["page"] for p in response.context["pages_with_progress"]]
        assert test_page in pages

    def test_exists_in_all_languages_excludes_partial(
        self, admin_client, test_page, locale_en, locale_de, locale_es
    ):
        """Pages missing any active locale are excluded by the 'All languages' filter."""
        # Only create a de translation, leaving es missing
        with patch.object(transaction, "on_commit", side_effect=lambda func: func()):
            source, _ = TranslationSource.get_or_create_from_instance(test_page)
            t, _ = Translation.objects.get_or_create(
                source=source, target_locale=locale_de
            )
            t.save_target(publish=True)

        url = reverse("wagtail_localize_dashboard:dashboard")

        response = admin_client.get(url, {"exists_in_language": "__all__"})
        assert response.status_code == 200
        pages = [p["page"] for p in response.context["pages_with_progress"]]
        assert test_page not in pages

    def test_exists_in_all_languages_checks_all_locales(
        self, admin_client, test_page, locale_en, locale_de, locale_es
    ):
        """
        Make sure that the "All languages" filter really checks all languages.


        If a page has a translation in all active locales except 1, but has a translation
        in an inactive locales, it should not show up in the results.
        """
        # zh has a Locale object but is not in WAGTAIL_CONTENT_LANGUAGES
        locale_zh, _ = Locale.objects.get_or_create(language_code="zh")
        # Locale.objects.count() is now 4 (en, de, es, zh)

        with patch.object(transaction, "on_commit", side_effect=lambda func: func()):
            source, _ = TranslationSource.get_or_create_from_instance(test_page)
            # de + zh gives 3 distinct locales (including the source en), but es is missing
            for locale in [locale_de, locale_zh]:
                t, _ = Translation.objects.get_or_create(
                    source=source, target_locale=locale
                )
                t.save_target(publish=True)
        # The test_page does not have a translation in "es".
        assert not Page.objects.filter(
            translation_key=test_page.translation_key,
            locale__language_code="es",
        ).exists()

        url = reverse("wagtail_localize_dashboard:dashboard")

        response = admin_client.get(url, {"exists_in_language": "__all__"})
        assert response.status_code == 200
        # Since the test_page does not have a translation in one of the active locales,
        # it should not be in the results when filtering for 'exists in all languages'.
        pages = [p["page"] for p in response.context["pages_with_progress"]]
        assert test_page not in pages

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
