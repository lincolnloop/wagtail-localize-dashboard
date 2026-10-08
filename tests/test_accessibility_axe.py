"""
Automated accessibility tests using selenium-axe-python.

These tests use axe-core (via selenium-axe-python) to automatically detect
accessibility violations in the translation dashboard.

To run these tests:
    pip install selenium selenium-axe-python
    pytest tests/test_accessibility_axe.py -m accessibility

Note: These tests require a web browser (Chrome/Firefox) to be available.
"""

import json
from urllib.parse import urlparse

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client, override_settings
from django.urls import reverse
from wagtail.models import Locale, Page
from wagtail.users.models import UserProfile

from tests.models import SampleSnippet
from wagtail_localize_dashboard.models import (
    SnippetTranslationProgress,
    TranslationProgress,
)

# These tests drive a real browser. The dependencies ship in the
# `accessibility` extra, not in the test extras, so the version matrix does
# not carry a browser stack it never uses. Guarding the import skips this
# module where they are absent instead of failing the whole run at collection.
webdriver = pytest.importorskip("selenium.webdriver")
Options = pytest.importorskip("selenium.webdriver.chrome.options").Options
Axe = pytest.importorskip("selenium_axe_python").Axe

User = get_user_model()


class DashboardAccessibilityMixin:
    """
    Shared axe-core test methods for both dashboard views.

    Concrete subclasses must define:
        DASHBOARD_URL_NAME  -- Django URL name for the dashboard
    And implement:
        _clear_progress_records()        -- delete model-specific progress rows
        test_filtered_dashboard_accessibility()  -- filtered-state check with explicit params
    """

    DASHBOARD_URL_NAME = None

    def _url(self, params=""):
        path = reverse(self.DASHBOARD_URL_NAME)
        if params:
            path = f"{path}?{params}"
        return f"{self.live_server_url}{path}"

    def _open(self, params=""):
        """Log in, open the dashboard, and refuse to audit anything else."""
        self._login()
        self.driver.get(self._url(params))

        # Make sure that the test is on the dashboard, rather than a login form,
        # a 404 page, etc.
        expected = reverse(self.DASHBOARD_URL_NAME)
        actual = urlparse(self.driver.current_url).path
        assert actual == expected, (
            f"Expected to audit {expected}, but the browser is on {actual}. "
            "Auditing that page would pass vacuously."
        )

        # Make sure the dashboard stylesheet was actually applied.
        rules = self.driver.execute_script(
            "const s = [...document.styleSheets]"
            "  .find(s => (s.href || '').includes('dashboard.css'));"
            "try { return s ? s.cssRules.length : 0 } catch (e) { return 0 }"
        )
        assert rules > 0, (
            "dashboard.css did not load, so the audit would run against "
            "unstyled markup and tell us nothing about what users see."
        )

        # Make sure the theme we asked for is the theme being used.
        html_class = self.driver.execute_script(
            "return document.documentElement.className"
        )
        assert f"w-theme-{self.theme}" in html_class, (
            f"Expected the admin to render in the {self.theme} theme, but "
            f"<html> carries {html_class!r}."
        )

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_no_critical_violations(self):
        """Dashboard has no critical or serious axe violations."""
        self._open()

        violations = self._run_axe()["violations"]
        critical = [v for v in violations if v["impact"] in ("critical", "serious")]

        if critical:
            details = "\n".join(
                f"- {v['id']}: {v['description']} (Impact: {v['impact']})\n"
                f"  Help: {v['helpUrl']}\n"
                f"  Affected elements: {len(v['nodes'])}\n"
                f"  Tags: {', '.join(v['tags'])}"
                for v in critical
            )
            self.fail(
                f"Found {len(critical)} critical accessibility violations:\n{details}"
            )

    def _test_wcag_aa_compliance(self):
        """Test that the dashboard meets WCAG 2.1 Level AA standards."""
        self._open()

        results = self._run_axe(
            options={
                "runOnly": {
                    "type": "tag",
                    "values": ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"],
                }
            }
        )

        violations = results["violations"]
        if violations:
            summary = "\n".join(
                f"- {v['id']}: {v['description']} (Impact: {v.get('impact', 'unknown')})"
                for v in violations
            )
            self.fail(f"WCAG 2.1 AA violations found:\n{summary}")

    def test_wcag_aa_compliance_dark_theme(self):
        """Test WCAG compliance in a dark theme."""
        self._set_theme("dark")
        self._test_wcag_aa_compliance()

    def test_wcag_aa_compliance_light_theme(self):
        """Test WCAG compliance in a light theme."""
        self._set_theme("light")
        self._test_wcag_aa_compliance()

    def test_wcag_aaa_best_effort(self):
        """WCAG 2.1 Level AAA — informational only, does not fail the suite."""
        self._open()

        results = self._run_axe(
            options={
                "runOnly": {
                    "type": "tag",
                    "values": ["wcag2aaa", "wcag21aaa"],
                }
            }
        )

        if results["violations"]:
            print("\nWCAG 2.1 AAA violations (informational):")
            for v in results["violations"]:
                print(f"  - {v['id']}: {v['description']}")

    def test_keyboard_accessibility(self):
        """All interactive elements are keyboard accessible."""
        self._open()

        results = self._run_axe(
            options={"runOnly": {"type": "tag", "values": ["keyboard"]}}
        )

        assert len(results["violations"]) == 0, (
            f"Keyboard accessibility violations found:\n{results['violations']}"
        )

    def test_screen_reader_compatibility(self):
        """Dashboard has no critical/serious screen-reader compatibility issues."""
        self._open()

        results = self._run_axe(
            options={
                "runOnly": {
                    "type": "tag",
                    "values": ["best-practice", "forms", "aria", "semantics"],
                }
            }
        )

        violations = [
            v for v in results["violations"] if v["impact"] in ("critical", "serious")
        ]
        if violations:
            details = "\n".join(f"- {v['id']}: {v['description']}" for v in violations)
            self.fail(f"Screen reader compatibility issues found:\n{details}")

    def _test_color_contrast(self):
        """Text and UI elements have sufficient color contrast."""
        self._open()

        results = self._run_axe(
            options={
                "runOnly": {"type": "tag", "values": ["cat.color"]},
                "rules": {"color-contrast-enhanced": {"enabled": False}},
            }
        )

        violations = results["violations"]
        if violations:
            issues = "\n".join(
                f"- {v['id']}: {v['description']} (Impact: {v.get('impact', 'unknown')})"
                for v in violations
            )
            self.fail(f"Color contrast violations:\n{issues}")

    def test_color_contrast_dark_theme(self):
        """Test contrast in a dark theme."""
        self._set_theme("dark")
        self._test_color_contrast()

    def test_color_contrast_light_theme(self):
        """Test contrast in a light theme."""
        self._set_theme("light")
        self._test_color_contrast()

    def test_table_accessibility(self):
        """The dashboard table is accessible."""
        self._open()

        results = self._run_axe(
            options={"runOnly": {"type": "tag", "values": ["tables"]}}
        )

        violations = results["violations"]
        if violations:
            issues = "\n".join(f"- {v['id']}: {v['description']}" for v in violations)
            self.fail(f"Table accessibility violations:\n{issues}")

    def test_form_accessibility(self):
        """Filter form controls have no critical/serious accessibility issues."""
        self._open()

        results = self._run_axe(
            options={"runOnly": {"type": "tag", "values": ["forms"]}}
        )

        violations = [
            v for v in results["violations"] if v["impact"] in ("critical", "serious")
        ]
        if violations:
            issues = "\n".join(f"- {v['id']}: {v['description']}" for v in violations)
            self.fail(f"Form accessibility violations:\n{issues}")

    def test_landmarks_and_regions(self):
        """Page has proper landmark regions for navigation."""
        self._open()

        results = self._run_axe(
            options={"runOnly": {"type": "tag", "values": ["region"]}}
        )

        violations = results["violations"]
        if violations:
            issues = "\n".join(f"- {v['id']}: {v['description']}" for v in violations)
            self.fail(f"Landmark/region violations:\n{issues}")

    def test_language_attributes(self):
        """HTML language attributes are properly set."""
        self._open()

        results = self._run_axe(
            options={"runOnly": {"type": "tag", "values": ["language"]}}
        )

        assert len(results["violations"]) == 0, (
            f"Language attribute violations:\n{results['violations']}"
        )

    def test_empty_dashboard_accessibility(self):
        """Dashboard has no critical/serious violations in the empty state."""
        self._clear_progress_records()

        self._open()

        results = self._run_axe()
        violations = [
            v for v in results["violations"] if v["impact"] in ("critical", "serious")
        ]

        if violations:
            details = "\n".join(f"- {v['id']}: {v['description']}" for v in violations)
            self.fail(f"Accessibility violations in empty dashboard state:\n{details}")

    def test_filtered_dashboard_accessibility(self):
        """Dashboard has no critical/serious violations when filters are applied.

        Subclasses must override this with view-specific filter parameters.
        """
        raise NotImplementedError(
            "Override this in each subclass with explicit filter params."
        )


class BaseDashboardAccessibility(StaticLiveServerTestCase):
    """WebDriver setup/teardown and shared test helpers."""

    # One translation per locale, covering every visual state the templates can
    # produce. percent_translated picks the badge color (100 -> btn-success,
    # 80-99 -> btn-warning, below 80 -> btn-danger), and
    BADGE_STATES = (
        # percent_translated, percent_published, has_unpublished_translations, language_code
        (100, 100, False, "fr"),
        (85, 85, False, "es"),
        (75, 75, False, "de"),
        (100, 60, True, "it"),
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")

        cls.driver = webdriver.Chrome(options=chrome_options)
        cls.driver.implicitly_wait(10)

    @classmethod
    def tearDownClass(cls):
        cls.driver.quit()
        super().tearDownClass()

    def setUp(self):
        super().setUp()

        self.user = User.objects.create_superuser(
            username="testadmin", email="admin@test.com", password="testpass123"
        )

        self.locale_en, _ = Locale.objects.get_or_create(language_code="en")
        self.locale_de, _ = Locale.objects.get_or_create(language_code="de")
        self.locale_es, _ = Locale.objects.get_or_create(language_code="es")
        self.locale_fr, _ = Locale.objects.get_or_create(language_code="fr")
        self.locale_it, _ = Locale.objects.get_or_create(language_code="it")

        self._set_theme("light")

    def _set_theme(self, theme):
        """Set the color theme (dark or light). Wagtail determines it from the admin user's profile."""
        self.theme = theme
        profile = UserProfile.get_for_user(self.user)
        profile.theme = theme
        profile.save()

    def _login(self):
        """Authenticate by handing the browser a ready-made session cookie."""
        client = Client()
        client.force_login(self.user)

        self.driver.get(f"{self.live_server_url}/admin/login/")
        self.driver.add_cookie(
            {
                "name": settings.SESSION_COOKIE_NAME,
                "value": client.cookies[settings.SESSION_COOKIE_NAME].value,
                "path": "/",
            }
        )

    def _run_axe(self, options=None):
        axe = Axe(self.driver)
        axe.inject()
        # Make sure we turn "options" into JSON before sending to axe.run().
        if options is not None:
            options = json.dumps(options)
        return axe.run(options=options)


@pytest.mark.accessibility
@pytest.mark.selenium
class TestPageDashboardAccessibility(
    DashboardAccessibilityMixin, BaseDashboardAccessibility
):
    """Accessibility tests for the pages translation progress dashboard."""

    DASHBOARD_URL_NAME = "wagtail_localize_dashboard:dashboard"

    def setUp(self):
        super().setUp()

        try:
            root_page = Page.objects.get(depth=1)
        except Page.DoesNotExist:
            root_page = Page(
                title="Root",
                slug="root",
                content_type=ContentType.objects.get_for_model(Page),
                path="0001",
                depth=1,
                numchild=0,
                url_path="/",
            )
            root_page.save()

        # The dashboard lists pages at depth > 2, which skips the root and the
        # site's home page. We attach the test page to a home page, to make sure
        # that the dashboard does not render an empty table.
        self.parent_page = Page(
            title="Axe Home", slug="axe-home", locale=self.locale_en
        )
        root_page.add_child(instance=self.parent_page)

        self.test_page = Page(
            title="Test Page", slug="test-page", locale=self.locale_en
        )
        self.parent_page.add_child(instance=self.test_page)

        # Make sure there is a badge of each state.
        translations = []
        for (
            translated,
            published,
            has_unpublished_translations,
            language_code,
        ) in self.BADGE_STATES:
            locale = Locale.objects.get(language_code=language_code)
            translated_page = self.test_page.copy_for_translation(
                locale, copy_parents=True
            )
            translated_page.save()
            translations.append(
                (translated, published, has_unpublished_translations, translated_page)
            )

        # Note: since there aren't actually translated strings for these pages,
        # make sure that the page doesn't get saved after this point, or the
        # signals will recompute this percentage.
        for (
            translated,
            published,
            has_unpublished_translations,
            translated_page,
        ) in translations:
            TranslationProgress.objects.update_or_create(
                source_page=self.test_page,
                translated_page=translated_page,
                defaults={
                    "percent_translated": translated,
                    "percent_published": published,
                    "has_unpublished_translations": has_unpublished_translations,
                },
            )

    def _clear_progress_records(self):
        TranslationProgress.objects.all().delete()

    def test_filtered_dashboard_accessibility(self):
        """Pages dashboard has no critical/serious violations when search and language filters are applied."""
        self._open("search=test&original_language=en")

        results = self._run_axe()
        violations = [
            v for v in results["violations"] if v["impact"] in ("critical", "serious")
        ]

        if violations:
            details = "\n".join(f"- {v['id']}: {v['description']}" for v in violations)
            self.fail(
                f"Accessibility violations in filtered pages dashboard:\n{details}"
            )


@pytest.mark.accessibility
@pytest.mark.selenium
@override_settings(WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"])
class TestSnippetDashboardAccessibility(
    DashboardAccessibilityMixin, BaseDashboardAccessibility
):
    """Accessibility tests for the snippet translation progress dashboard."""

    DASHBOARD_URL_NAME = "wagtail_localize_dashboard:snippet_dashboard"

    def setUp(self):
        super().setUp()

        self.source_snippet = SampleSnippet.objects.create(
            locale=self.locale_en, heading="Test Snippet"
        )
        ct = ContentType.objects.get_for_model(SampleSnippet)

        # Make sure there is a badge of each state.
        # Same two passes as the page fixture, and for the same reason.
        translations = []
        for (
            translated,
            published,
            has_unpublished_translations,
            language_code,
        ) in self.BADGE_STATES:
            locale = Locale.objects.get(language_code=language_code)
            translated_snippet = self.source_snippet.copy_for_translation(locale)
            translated_snippet.save()
            translations.append(
                (
                    translated,
                    published,
                    has_unpublished_translations,
                    locale,
                    translated_snippet,
                )
            )

        for (
            translated,
            published,
            has_unpublished_translations,
            locale,
            translated_snippet,
        ) in translations:
            SnippetTranslationProgress.objects.update_or_create(
                content_type=ct,
                source_object_id=self.source_snippet.pk,
                translated_object_id=translated_snippet.pk,
                translated_locale=locale,
                defaults={
                    "percent_translated": translated,
                    "percent_published": published,
                    "has_unpublished_translations": has_unpublished_translations,
                },
            )

        # A snippet with no translations, to exercise the "No translations" row state.
        SampleSnippet.objects.create(
            locale=self.locale_en, heading="Untranslated Snippet"
        )

    def _clear_progress_records(self):
        SnippetTranslationProgress.objects.all().delete()

    def test_filtered_dashboard_accessibility(self):
        """Snippet dashboard has no critical/serious violations when a language filter is applied."""
        self._open("original_language=en")

        results = self._run_axe()
        violations = [
            v for v in results["violations"] if v["impact"] in ("critical", "serious")
        ]

        if violations:
            details = "\n".join(f"- {v['id']}: {v['description']}" for v in violations)
            self.fail(
                f"Accessibility violations in filtered snippet dashboard:\n{details}"
            )
