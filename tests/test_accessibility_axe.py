"""
Automated accessibility tests using selenium-axe-python.

These tests use axe-core (via selenium-axe-python) to automatically detect
accessibility violations in the translation dashboard.

To run these tests:
    pip install selenium selenium-axe-python
    pytest tests/test_accessibility_axe.py -m accessibility

Note: These tests require a web browser (Chrome/Firefox) to be available.
"""

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import LiveServerTestCase, override_settings
from django.urls import reverse

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium_axe_python import Axe
from wagtail.models import Locale, Page
from wagtail_localize_dashboard.models import (
    SnippetTranslationProgress,
    TranslationProgress,
)

from tests.models import SampleSnippet

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

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_no_critical_violations(self):
        """Dashboard has no critical or serious axe violations."""
        self._login()
        self.driver.get(self._url())

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

    def test_wcag_aa_compliance(self):
        """Dashboard meets WCAG 2.1 Level AA standards."""
        self._login()
        self.driver.get(self._url())

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

    def test_wcag_aaa_best_effort(self):
        """WCAG 2.1 Level AAA — informational only, does not fail the suite."""
        self._login()
        self.driver.get(self._url())

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
        self._login()
        self.driver.get(self._url())

        results = self._run_axe(
            options={"runOnly": {"type": "tag", "values": ["keyboard"]}}
        )

        assert len(results["violations"]) == 0, (
            f"Keyboard accessibility violations found:\n{results['violations']}"
        )

    def test_screen_reader_compatibility(self):
        """Dashboard has no critical/serious screen-reader compatibility issues."""
        self._login()
        self.driver.get(self._url())

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

    def test_color_contrast(self):
        """Text and UI elements have sufficient colour contrast."""
        self._login()
        self.driver.get(self._url())

        results = self._run_axe(
            options={"runOnly": {"type": "tag", "values": ["cat.color"]}}
        )

        violations = results["violations"]
        if violations:
            issues = "\n".join(
                f"- {v['id']}: {v['description']} (Impact: {v.get('impact', 'unknown')})"
                for v in violations
            )
            self.fail(f"Color contrast violations:\n{issues}")

    def test_table_accessibility(self):
        """The dashboard table is accessible."""
        self._login()
        self.driver.get(self._url())

        results = self._run_axe(
            options={"runOnly": {"type": "tag", "values": ["tables"]}}
        )

        violations = results["violations"]
        if violations:
            issues = "\n".join(f"- {v['id']}: {v['description']}" for v in violations)
            self.fail(f"Table accessibility violations:\n{issues}")

    def test_form_accessibility(self):
        """Filter form controls have no critical/serious accessibility issues."""
        self._login()
        self.driver.get(self._url())

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
        self._login()
        self.driver.get(self._url())

        results = self._run_axe(
            options={"runOnly": {"type": "tag", "values": ["region"]}}
        )

        violations = results["violations"]
        if violations:
            issues = "\n".join(f"- {v['id']}: {v['description']}" for v in violations)
            self.fail(f"Landmark/region violations:\n{issues}")

    def test_language_attributes(self):
        """HTML language attributes are properly set."""
        self._login()
        self.driver.get(self._url())

        results = self._run_axe(
            options={"runOnly": {"type": "tag", "values": ["language"]}}
        )

        assert len(results["violations"]) == 0, (
            f"Language attribute violations:\n{results['violations']}"
        )

    def test_empty_dashboard_accessibility(self):
        """Dashboard has no critical/serious violations in the empty state."""
        self._clear_progress_records()

        self._login()
        self.driver.get(self._url())

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


class BaseDashboardAccessibility(LiveServerTestCase):
    """WebDriver setup/teardown and shared test helpers."""

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

    def _login(self):
        self.driver.get(f"{self.live_server_url}/admin/login/")
        self.driver.find_element("id", "id_username").send_keys("testadmin")
        self.driver.find_element("id", "id_password").send_keys("testpass123")
        self.driver.find_element("css selector", "button[type='submit']").click()

    def _run_axe(self, options=None):
        axe = Axe(self.driver)
        axe.inject()
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

        self.test_page = Page(
            title="Test Page", slug="test-page", locale=self.locale_en
        )
        root_page.add_child(instance=self.test_page)

        self.translated_page = self.test_page.copy_for_translation(
            self.locale_de, copy_parents=True
        )
        self.translated_page.save()

        TranslationProgress.objects.update_or_create(
            source_page=self.test_page,
            translated_page=self.translated_page,
            defaults={"percent_translated": 75},
        )

    def _clear_progress_records(self):
        TranslationProgress.objects.all().delete()

    def test_filtered_dashboard_accessibility(self):
        """Pages dashboard has no critical/serious violations when search and language filters are applied."""
        self._login()
        self.driver.get(self._url("search=test&original_language=en"))

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
        self.translated_snippet = self.source_snippet.copy_for_translation(
            self.locale_de
        )
        self.translated_snippet.save()

        ct = ContentType.objects.get_for_model(SampleSnippet)
        SnippetTranslationProgress.objects.update_or_create(
            content_type=ct,
            source_object_id=self.source_snippet.pk,
            translated_object_id=self.translated_snippet.pk,
            translated_locale=self.locale_de,
            defaults={"percent_translated": 75},
        )

        # A snippet with no translations, to exercise the "No translations" row state.
        SampleSnippet.objects.create(
            locale=self.locale_en, heading="Untranslated Snippet"
        )

    def _clear_progress_records(self):
        SnippetTranslationProgress.objects.all().delete()

    def test_filtered_dashboard_accessibility(self):
        """Snippet dashboard has no critical/serious violations when a language filter is applied."""
        self._login()
        self.driver.get(self._url("original_language=en"))

        results = self._run_axe()
        violations = [
            v for v in results["violations"] if v["impact"] in ("critical", "serious")
        ]

        if violations:
            details = "\n".join(f"- {v['id']}: {v['description']}" for v in violations)
            self.fail(
                f"Accessibility violations in filtered snippet dashboard:\n{details}"
            )
