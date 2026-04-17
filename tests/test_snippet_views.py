"""Tests for the snippet translation dashboard view."""

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from tests.models import DraftStateSnippet, SampleSnippet
from wagtail.models import Locale
from wagtail_localize_dashboard.forms import SnippetProgressFilterForm
from wagtail_localize_dashboard.models import SnippetTranslationProgress

pytestmark = [pytest.mark.django_db]

SNIPPET_DASHBOARD_URL_NAME = "wagtail_localize_dashboard:snippet_dashboard"

COLUMN_FILTER_OPTIONS = [
    ("group_a", "Group A", ["de", "fr"]),
    ("group_b", "Group B", ["es"]),
]


class TestSnippetProgressDashboardView:
    """Tests for SnippetProgressDashboardView."""

    def test_requires_login(self, client):
        """Unauthenticated users are redirected to login."""
        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
        response = client.get(url)

        # Should redirect to login
        assert response.status_code == 302
        assert response.url == f"/django-admin/login/?next={url}"

    def test_accessible_to_admin(self, admin_client):
        """Admin users can access the snippet dashboard."""
        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
        response = admin_client.get(url)
        assert response.status_code == 200
        assert (
            b"Translation Dashboard" in response.content
            or b"Translations" in response.content
        )

    def test_accessible_to_staff(self, staff_client):
        """Staff users can access the snippet dashboard."""
        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
        response = staff_client.get(url)
        assert response.status_code == 200
        assert (
            b"Translation Dashboard" in response.content
            or b"Translations" in response.content
        )

    def test_non_staff_user_is_redirected(self, client, regular_user):
        """Non-staff users are redirected to login."""
        client.force_login(regular_user)
        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
        response = client.get(url)

        # Should redirect to login
        assert response.status_code == 302
        assert response.url == f"/django-admin/login/?next={url}"

    def test_returns_empty_list_without_tracked_snippets(self, admin_client):
        """Returns an empty snippet list when no models are tracked."""
        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
        response = admin_client.get(url)
        assert response.status_code == 200
        assert response.context["snippets_with_progress"] == []

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
    )
    def test_shows_tracked_snippets(self, admin_client, sample_snippet):
        """Shows original snippets for tracked models."""
        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
        response = admin_client.get(url)

        assert response.status_code == 200
        snippets_data = response.context["snippets_with_progress"]
        assert len(snippets_data) == 1
        assert snippets_data[0]["snippet"] == sample_snippet

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
    )
    def test_snippet_name_appears_in_html(self, admin_client, sample_snippet):
        """Snippet string representation appears in the rendered HTML."""
        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
        response = admin_client.get(url)

        assert b"Sample Snippet" in response.content

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
    )
    def test_context_has_filter_form(self, admin_client):
        """Context includes the snippet filter form."""
        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
        response = admin_client.get(url)
        assert "filter_form" in response.context
        assert isinstance(response.context["filter_form"], SnippetProgressFilterForm)

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
    )
    def test_has_draft_state_false_for_non_draft_model(
        self, admin_client, sample_snippet
    ):
        """has_draft_state is False for models without DraftStateMixin."""
        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
        response = admin_client.get(url)

        snippets_data = response.context["snippets_with_progress"]
        assert len(snippets_data) == 1
        assert snippets_data[0]["has_draft_state"] is False

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.DraftStateSnippet"]
    )
    def test_has_draft_state_true_for_draft_model(self, admin_client, locale_en):
        """has_draft_state is True for models that use DraftStateMixin."""

        DraftStateSnippet.objects.create(locale=locale_en, title="Draft Snippet")
        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
        response = admin_client.get(url)

        snippets_data = response.context["snippets_with_progress"]
        assert len(snippets_data) == 1
        assert snippets_data[0]["has_draft_state"] is True

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
    )
    def test_translations_empty_when_no_progress(self, admin_client, sample_snippet):
        """Translation list is empty when no SnippetTranslationProgress records exist."""
        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
        response = admin_client.get(url)

        snippets_data = response.context["snippets_with_progress"]
        assert snippets_data[0]["translations"] == []

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
    )
    def test_only_shows_original_snippets_not_translations(
        self, admin_client, sample_snippet, sample_snippet_de
    ):
        """Only the original (lowest-pk) snippet per translation_key is shown."""
        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
        response = admin_client.get(url)

        snippets_data = response.context["snippets_with_progress"]
        assert len(snippets_data) == 1
        assert snippets_data[0]["snippet"].pk == sample_snippet.pk

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
    )
    def test_shows_translation_progress(
        self, admin_client, sample_snippet, sample_snippet_de, locale_de
    ):
        """Test that the snippet dashboard shows translation progress."""
        ct = ContentType.objects.get_for_model(SampleSnippet)
        SnippetTranslationProgress.objects.create(
            content_type=ct,
            source_object_id=sample_snippet.pk,
            translated_object_id=sample_snippet_de.pk,
            translated_locale=locale_de,
            percent_translated=75,
        )

        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
        response = admin_client.get(url)

        assert response.status_code == 200
        assert b"75" in response.content or b"75%" in response.content
        snippets_data = response.context["snippets_with_progress"]
        assert len(snippets_data) == 1
        assert snippets_data[0]["snippet"] == sample_snippet
        translations = snippets_data[0]["translations"]
        assert [t["percent_translated"] for t in translations] == [75]
        assert [t["locale"] for t in translations] == ["de"]

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
    )
    def test_language_filter(self, admin_client, sample_snippet, sample_snippet_de):
        """Filtering by original_language shows only snippets in that locale."""
        url = reverse(SNIPPET_DASHBOARD_URL_NAME)

        # Filtering by English should show the source snippet.
        response = admin_client.get(url, {"original_language": "en"})
        assert response.status_code == 200
        snippets = [d["snippet"] for d in response.context["snippets_with_progress"]]
        assert snippets == [sample_snippet]

        # Filtering by German should show no results (translated copy is not original).
        response = admin_client.get(url, {"original_language": "de"})
        assert response.status_code == 200
        assert response.context["snippets_with_progress"] == []

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
    )
    def test_translation_key_filter(self, admin_client, locale_en):
        """Filtering by translation_key returns only the matching snippet."""
        snippet = SampleSnippet.objects.create(locale=locale_en, heading="Unique")
        SampleSnippet.objects.create(locale=locale_en, heading="Other")

        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
        response = admin_client.get(url, {"translation_key": snippet.translation_key})

        assert response.status_code == 200
        snippets = [d["snippet"] for d in response.context["snippets_with_progress"]]
        assert snippets == [snippet]

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
    )
    def test_pagination(self, admin_client, locale_en):
        """Dashboard paginates results correctly."""
        for i in range(60):
            SampleSnippet.objects.create(locale=locale_en, heading=f"Snippet {i:03d}")

        url = reverse(SNIPPET_DASHBOARD_URL_NAME)

        response = admin_client.get(url)
        assert response.status_code == 200

        response = admin_client.get(url, {"page": 2})
        assert response.status_code == 200

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
    )
    def test_empty_state(self, admin_client):
        """Dashboard shows empty state message when no snippets exist."""
        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
        response = admin_client.get(url)

        assert response.status_code == 200
        assert response.context["snippets_with_progress"] == []
        assert "No snippets found." in response.content.decode()

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
    )
    def test_multiple_locales(
        self, admin_client, locale_en, locale_de, locale_es, locale_fr
    ):
        """Dashboard shows progress for all translation locales."""
        source = SampleSnippet.objects.create(locale=locale_en, heading="Multi")
        ct = ContentType.objects.get_for_model(SampleSnippet)
        for locale in [locale_de, locale_es, locale_fr]:
            translated = source.copy_for_translation(locale)
            translated.save()
            SnippetTranslationProgress.objects.create(
                content_type=ct,
                source_object_id=source.pk,
                translated_object_id=translated.pk,
                translated_locale=locale,
                percent_translated=50,
            )

        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
        response = admin_client.get(url)

        assert response.status_code == 200
        snippets_data = response.context["snippets_with_progress"]
        assert [d["snippet"] for d in snippets_data] == [source]
        translation_locales = {t["locale"] for t in snippets_data[0]["translations"]}
        assert translation_locales == {"de", "es", "fr"}

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
    )
    def test_query_count_optimized(
        self, admin_client, locale_en, locale_de, locale_es, locale_fr
    ):
        """Dashboard uses a bounded number of queries (no N+1 problem)."""
        ct = ContentType.objects.get_for_model(SampleSnippet)
        num_snippets = 5

        for i in range(num_snippets):
            source = SampleSnippet.objects.create(
                locale=locale_en, heading=f"Snippet {i:03d}"
            )
            for locale in [locale_de, locale_es, locale_fr]:
                translated = source.copy_for_translation(locale)
                translated.save()
                SnippetTranslationProgress.objects.create(
                    content_type=ct,
                    source_object_id=source.pk,
                    translated_object_id=translated.pk,
                    translated_locale=locale,
                    percent_translated=50,
                )

        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
        with CaptureQueriesContext(connection) as queries:
            response = admin_client.get(url)

        assert response.status_code == 200
        num_queries = len(queries)
        # We should have <= 11 queries total
        expected_max_num_queries = 11
        assert num_queries <= expected_max_num_queries, (
            f"Too many queries: {num_queries}. Expected <= {expected_max_num_queries}. Queries:\n"
            + "\n".join([q["sql"] for q in queries])
        )
        assert len(response.context["snippets_with_progress"]) == num_snippets

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
    )
    def test_edit_links(self, admin_client, sample_snippet):
        """Dashboard includes edit links for each snippet."""
        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
        response = admin_client.get(url)

        assert response.status_code == 200
        ct = ContentType.objects.get_for_model(SampleSnippet)
        edit_url = reverse(
            f"wagtailsnippets_{ct.app_label}_{ct.model}:edit",
            args=[sample_snippet.pk],
        )
        assert edit_url.encode() in response.content

    @override_settings(WAGTAIL_LOCALIZE_DASHBOARD_COLUMN_FILTER_OPTIONS=[])
    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
    )
    def test_column_filter_absent_when_setting_empty(
        self, admin_client, sample_snippet
    ):
        """Column filter field is absent when COLUMN_FILTER_OPTIONS is empty."""
        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
        response = admin_client.get(url)
        assert "column_filter" not in response.context["filter_form"].fields

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_COLUMN_FILTER_OPTIONS=COLUMN_FILTER_OPTIONS,
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"],
    )
    def test_column_filter_present_when_setting_configured(
        self, admin_client, sample_snippet
    ):
        """Column filter field is present with correct choices when configured."""
        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
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
        WAGTAIL_LOCALIZE_DASHBOARD_COLUMN_FILTER_OPTIONS=COLUMN_FILTER_OPTIONS,
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"],
    )
    def test_column_filter_no_selection_shows_all(
        self, admin_client, sample_snippet_de_progress
    ):
        """With no column filter selected, all translations are shown."""
        url = reverse(SNIPPET_DASHBOARD_URL_NAME)

        response = admin_client.get(url, {"column_filter": ""})
        assert len(response.context["snippets_with_progress"]) == 1
        translations = response.context["snippets_with_progress"][0]["translations"]
        assert len(translations) == 1
        assert translations[0]["locale"] == "de"

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_COLUMN_FILTER_OPTIONS=COLUMN_FILTER_OPTIONS,
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"],
    )
    def test_column_filter_shows_only_matching_locales(
        self, admin_client, locale_en, locale_de, locale_es, locale_fr
    ):
        """Selecting a column filter shows only matching locale buttons."""
        source = SampleSnippet.objects.create(locale=locale_en, heading="Source")
        ct = ContentType.objects.get_for_model(SampleSnippet)
        for locale in [locale_de, locale_es, locale_fr]:
            translated = source.copy_for_translation(locale)
            translated.save()
            SnippetTranslationProgress.objects.create(
                content_type=ct,
                source_object_id=source.pk,
                translated_object_id=translated.pk,
                translated_locale=locale,
                percent_translated=50,
            )

        url = reverse(SNIPPET_DASHBOARD_URL_NAME)

        # group_a includes de and fr
        response = admin_client.get(url, {"column_filter": "group_a"})
        assert len(response.context["snippets_with_progress"]) == 1
        translations = response.context["snippets_with_progress"][0]["translations"]
        locales = {t["locale"] for t in translations}
        assert locales == {"de", "fr"}

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_COLUMN_FILTER_OPTIONS=COLUMN_FILTER_OPTIONS,
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"],
    )
    def test_column_filter_rows_with_no_matches_still_appear(
        self, admin_client, sample_snippet, sample_snippet_de, locale_de
    ):
        """Rows with no matching translations still appear (not hidden)."""
        ct = ContentType.objects.get_for_model(SampleSnippet)
        SnippetTranslationProgress.objects.create(
            content_type=ct,
            source_object_id=sample_snippet.pk,
            translated_object_id=sample_snippet_de.pk,
            translated_locale=locale_de,
            percent_translated=100,
        )

        url = reverse(SNIPPET_DASHBOARD_URL_NAME)

        # group_b only includes es, and there's no progress record for es
        response = admin_client.get(url, {"column_filter": "group_b"})
        snippets = response.context["snippets_with_progress"]
        assert len(snippets) == 1
        assert snippets[0]["snippet"] == sample_snippet
        assert snippets[0]["translations"] == []

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_COLUMN_FILTER_OPTIONS=COLUMN_FILTER_OPTIONS,
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"],
    )
    def test_column_filter_shows_active_message(self, admin_client, sample_snippet):
        """Active column filter displays a message with the chosen group label."""
        url = reverse(SNIPPET_DASHBOARD_URL_NAME)

        response = admin_client.get(url, {"column_filter": "group_a"})

        assert response.context["column_filter_label"] == "Group A"
        content = response.content.decode()
        assert "Only showing" in content
        assert "Group A" in content

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_COLUMN_FILTER_OPTIONS=COLUMN_FILTER_OPTIONS,
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"],
    )
    def test_column_filter_no_message_when_unset(self, admin_client, sample_snippet):
        """No active filter message when column filter is not selected."""
        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
        response = admin_client.get(url)
        assert response.context["column_filter_label"] == ""
        assert b"Only showing" not in response.content

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_COLUMN_FILTER_OPTIONS=COLUMN_FILTER_OPTIONS,
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"],
    )
    def test_column_filter_preserves_row_filters(
        self, admin_client, sample_snippet, sample_snippet_de
    ):
        """Row filter params (original_language) work alongside column filter."""
        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
        response = admin_client.get(
            url,
            {
                "original_language": "en",
                "column_filter": "group_a",
            },
        )

        assert response.status_code == 200
        snippets = response.context["snippets_with_progress"]
        assert len(snippets) == 1
        assert snippets[0]["snippet"] == sample_snippet

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
    )
    def test_sorting(self, admin_client, locale_en):
        """Snippets are sorted alphabetically by heading within the same model."""
        snippet_z = SampleSnippet.objects.create(
            locale=locale_en, heading="ZZZ Snippet"
        )
        snippet_a = SampleSnippet.objects.create(
            locale=locale_en, heading="AAA Snippet"
        )

        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
        response = admin_client.get(url)

        assert response.status_code == 200
        snippets = [d["snippet"] for d in response.context["snippets_with_progress"]]
        assert snippets == [snippet_a, snippet_z]

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
    )
    def test_exists_in_language_filter_specific(
        self, admin_client, locale_en, locale_de
    ):
        """exists_in_language filter keeps only originals that have a copy in that locale."""
        with_de = SampleSnippet.objects.create(locale=locale_en, heading="Has German")
        with_de.copy_for_translation(locale_de).save()

        without_de = SampleSnippet.objects.create(locale=locale_en, heading="No German")

        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
        response = admin_client.get(url, {"exists_in_language": "de"})

        snippets = [
            row["snippet"] for row in response.context["snippets_with_progress"]
        ]
        assert with_de in snippets
        assert without_de not in snippets

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
    )
    def test_exists_in_all_languages_filter(
        self, admin_client, locale_en, locale_de, locale_es, locale_fr
    ):
        """ALL_LANGUAGES filter keeps only originals translated into every active locale."""
        fully_translated = SampleSnippet.objects.create(
            locale=locale_en, heading="Full"
        )
        # Must have copies in all 4 configured languages (en, fr, de, es)
        for locale in [locale_de, locale_es, locale_fr]:
            fully_translated.copy_for_translation(locale).save()

        partially_translated = SampleSnippet.objects.create(
            locale=locale_en, heading="Partial"
        )
        partially_translated.copy_for_translation(locale_de).save()

        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
        response = admin_client.get(url, {"exists_in_language": "__all__"})

        snippets = [
            row["snippet"] for row in response.context["snippets_with_progress"]
        ]
        # partially_translated has no French copy, so it should be excluded from
        # the dashboard when using the from ALL_LANGUAGES filter.
        assert fully_translated in snippets
        assert partially_translated not in snippets

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"],
        WAGTAIL_LOCALIZE_DASHBOARD_CORE_LANGUAGES=[("de", "German")],
    )
    def test_exists_in_core_languages_filter(
        self, admin_client, locale_en, locale_de, locale_fr
    ):
        """CORE_LANGUAGES filter keeps only originals translated into every core language."""
        has_core = SampleSnippet.objects.create(locale=locale_en, heading="Has Core")
        has_core.copy_for_translation(locale_de).save()

        missing_core = SampleSnippet.objects.create(
            locale=locale_en, heading="Missing Core"
        )
        missing_core.copy_for_translation(locale_fr).save()  # French only, not German

        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
        response = admin_client.get(url, {"exists_in_language": "__core__"})

        snippets = [
            row["snippet"] for row in response.context["snippets_with_progress"]
        ]
        # missing_core has no German copy, so it should be excluded from
        # the dashboard when using the from CORE_LANGUAGES filter.
        assert has_core in snippets
        assert missing_core not in snippets

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=[
            "tests.SampleSnippet",
            "tests.DraftStateSnippet",
        ]
    )
    def test_snippet_type_filter_shows_only_matching_model(
        self, admin_client, locale_en
    ):
        """Selecting a snippet type hides snippets of other tracked models."""
        sample = SampleSnippet.objects.create(locale=locale_en, heading="Sample")
        draft = DraftStateSnippet.objects.create(locale=locale_en, title="Draft")

        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
        response = admin_client.get(url, {"snippet_type": "tests.SampleSnippet"})

        snippets = [
            row["snippet"] for row in response.context["snippets_with_progress"]
        ]
        assert sample in snippets
        assert draft not in snippets

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=[
            "tests.SampleSnippet",
            "tests.DraftStateSnippet",
        ]
    )
    def test_snippet_type_filter_absent_shows_all_models(self, admin_client, locale_en):
        """With no type filter, snippets from all tracked models appear."""
        sample = SampleSnippet.objects.create(locale=locale_en, heading="Sample")
        draft = DraftStateSnippet.objects.create(locale=locale_en, title="Draft")

        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
        response = admin_client.get(url)

        snippets = [
            row["snippet"] for row in response.context["snippets_with_progress"]
        ]
        assert sample in snippets
        assert draft in snippets

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
    )
    def test_snippet_type_field_present_when_one_model_tracked(
        self, admin_client, locale_en
    ):
        """snippet_type field is present even when only one model is tracked."""
        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
        response = admin_client.get(url)
        assert "snippet_type" in response.context["filter_form"].fields

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=[
            "tests.SampleSnippet",
            "tests.DraftStateSnippet",
        ]
    )
    def test_multiple_tracked_models_shown_together(self, admin_client, locale_en):
        """Snippets from all tracked models appear in the same view."""
        sample = SampleSnippet.objects.create(locale=locale_en, heading="Sample")
        draft = DraftStateSnippet.objects.create(locale=locale_en, title="Draft")

        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
        response = admin_client.get(url)

        instances = [
            row["snippet"] for row in response.context["snippets_with_progress"]
        ]
        assert sample in instances
        assert draft in instances

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
    )
    def test_explanatory_paragraph_for_status_column_present(
        self, admin_client, sample_snippet
    ):
        """Template includes the explanatory note about the empty Status column."""
        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
        response = admin_client.get(url)

        content = response.content.decode()
        assert "draft/live workflow" in content

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
    )
    def test_exists_in_all_languages_uses_active_locales(
        self, admin_client, locale_en, locale_de, locale_es
    ):
        """'All languages' filter matches snippets in all active Locale objects, not all configured languages."""
        # en, de, es are the only active locales — fr exists in WAGTAIL_CONTENT_LANGUAGES
        # but has no Locale object. A snippet with copies in en+de+es should match __all__.
        source = SampleSnippet.objects.create(locale=locale_en, heading="Source")
        source.copy_for_translation(locale_de).save()
        source.copy_for_translation(locale_es).save()
        # The source has a translation in each Locale.
        assert (
            SampleSnippet.objects.filter(translation_key=source.translation_key).count()
            == Locale.objects.count()
        )

        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
        response = admin_client.get(url, {"exists_in_language": "__all__"})

        assert response.status_code == 200
        snippets = [
            row["snippet"] for row in response.context["snippets_with_progress"]
        ]
        assert source in snippets

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
    )
    def test_exists_in_all_languages_excludes_partial(
        self, admin_client, locale_en, locale_de, locale_es
    ):
        """Snippets missing any active locale are excluded by the 'All languages' filter."""
        source = SampleSnippet.objects.create(locale=locale_en, heading="Source")
        source.copy_for_translation(locale_de).save()
        # The source does not have a translation in "es".
        assert not SampleSnippet.objects.filter(
            translation_key=source.translation_key,
            locale__language_code="es",
        ).exists()

        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
        response = admin_client.get(url, {"exists_in_language": "__all__"})

        assert response.status_code == 200
        snippets = [
            row["snippet"] for row in response.context["snippets_with_progress"]
        ]
        assert source not in snippets

    @override_settings(
        WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"]
    )
    def test_exists_in_all_languages_checks_all_locales(
        self, admin_client, locale_en, locale_de, locale_es
    ):
        """
        'All languages' really checks all active Locale objects.

        A snippet translated into en+de+zh (an unconfigured-but-active locale) should
        NOT match when es is also active, since es is missing.
        """
        locale_zh, _ = Locale.objects.get_or_create(language_code="zh")
        # Locale.objects.count() is now 4 (en, de, es, zh)

        source = SampleSnippet.objects.create(locale=locale_en, heading="Source")
        source.copy_for_translation(locale_de).save()
        source.copy_for_translation(locale_zh).save()
        # The source does not have a translation in "es".
        assert not SampleSnippet.objects.filter(
            translation_key=source.translation_key,
            locale__language_code="es",
        ).exists()

        url = reverse(SNIPPET_DASHBOARD_URL_NAME)
        response = admin_client.get(url, {"exists_in_language": "__all__"})

        assert response.status_code == 200
        # Because the source SampleSnippet does not have a translation in "es",
        # it is not in the results.
        snippets = [
            row["snippet"] for row in response.context["snippets_with_progress"]
        ]
        assert source not in snippets
