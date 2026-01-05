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
from django.test import LiveServerTestCase

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium_axe_python import Axe
from wagtail.models import Locale, Page
from wagtail_localize_dashboard.models import TranslationProgress

User = get_user_model()


@pytest.mark.accessibility
@pytest.mark.selenium
class TestDashboardAccessibility(LiveServerTestCase):
    """Test accessibility of the translation dashboard using axe-core."""

    @classmethod
    def setUpClass(cls):
        """Set up Selenium WebDriver for all tests."""
        super().setUpClass()

        # Configure Chrome to run in headless mode
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
        """Clean up WebDriver."""
        cls.driver.quit()
        super().tearDownClass()

    def setUp(self):
        """Set up test data before each test."""
        super().setUp()

        # Create a superuser for authentication
        self.user = User.objects.create_superuser(
            username="testadmin", email="admin@test.com", password="testpass123"
        )

        # Create locales
        self.locale_en, _ = Locale.objects.get_or_create(language_code="en")
        self.locale_de, _ = Locale.objects.get_or_create(language_code="de")
        self.locale_es, _ = Locale.objects.get_or_create(language_code="es")

        # Create Wagtail root page if it doesn't exist
        try:
            root_page = Page.objects.get(depth=1)
        except Page.DoesNotExist:
            # Create the root page
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

        # Create some test pages
        self.test_page = Page(
            title="Test Page", slug="test-page", locale=self.locale_en
        )
        root_page.add_child(instance=self.test_page)

        # Create a translated page
        self.translated_page = self.test_page.copy_for_translation(
            self.locale_de, copy_parents=True
        )
        self.translated_page.save()

        # Create or update translation progress records
        # (may already exist if signals created it)
        TranslationProgress.objects.update_or_create(
            source_page=self.test_page,
            translated_page=self.translated_page,
            defaults={"percent_translated": 75},
        )

    def _login(self):
        """Helper to log in the test user."""
        self.driver.get(f"{self.live_server_url}/admin/login/")
        username_input = self.driver.find_element("id", "id_username")
        password_input = self.driver.find_element("id", "id_password")

        username_input.send_keys("testadmin")
        password_input.send_keys("testpass123")

        self.driver.find_element("css selector", "button[type='submit']").click()

    def _run_axe(self, options=None):
        """Helper to run axe and return results."""
        axe = Axe(self.driver)
        axe.inject()
        return axe.run(options=options)

    def test_no_critical_violations(self):
        """Test that dashboard has no critical accessibility violations."""
        self._login()
        self.driver.get(f"{self.live_server_url}/admin/translations/")

        # Run axe accessibility tests
        results = self._run_axe()

        # Check for violations
        violations = results["violations"]

        # Assert no critical or serious violations
        critical_violations = [
            v for v in violations if v["impact"] in ("critical", "serious")
        ]

        if critical_violations:
            # Format violation details for debugging
            violation_details = "\n".join(
                [
                    f"- {v['id']}: {v['description']} (Impact: {v['impact']})\n"
                    f"  Help: {v['helpUrl']}\n"
                    f"  Affected elements: {len(v['nodes'])}\n"
                    f"  Tags: {', '.join(v['tags'])}"
                    for v in critical_violations
                ]
            )
            self.fail(
                f"Found {len(critical_violations)} critical accessibility violations:\n{violation_details}"
            )

    def test_wcag_aa_compliance(self):
        """Test that dashboard meets WCAG 2.1 Level AA standards."""
        self._login()
        self.driver.get(f"{self.live_server_url}/admin/translations/")

        # Run axe with WCAG 2.1 Level AA rules
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
            violation_summary = "\n".join(
                [
                    f"- {v['id']}: {v['description']} (Impact: {v.get('impact', 'unknown')})"
                    for v in violations
                ]
            )
            self.fail(f"WCAG 2.1 AA violations found:\n{violation_summary}")

    def test_wcag_aaa_best_effort(self):
        """Test WCAG 2.1 Level AAA (best effort, non-blocking)."""
        self._login()
        self.driver.get(f"{self.live_server_url}/admin/translations/")

        # Run axe with WCAG 2.1 Level AAA rules
        results = self._run_axe(
            options={
                "runOnly": {
                    "type": "tag",
                    "values": ["wcag2aaa", "wcag21aaa"],
                }
            }
        )

        violations = results["violations"]

        # AAA is aspirational, so we just log violations without failing
        if violations:
            print("\nWCAG 2.1 AAA violations (informational):")
            for v in violations:
                print(f"  - {v['id']}: {v['description']}")

    def test_keyboard_accessibility(self):
        """Test that all interactive elements are keyboard accessible."""
        self._login()
        self.driver.get(f"{self.live_server_url}/admin/translations/")

        # Run axe with keyboard accessibility rules
        results = self._run_axe(
            options={"runOnly": {"type": "tag", "values": ["keyboard"]}}
        )

        violations = results["violations"]

        assert len(violations) == 0, (
            f"Keyboard accessibility violations found:\n{violations}"
        )

    def test_screen_reader_compatibility(self):
        """Test that dashboard works well with screen readers."""
        self._login()
        self.driver.get(f"{self.live_server_url}/admin/translations/")

        # Check for proper labeling, semantics, and ARIA
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
            violation_details = "\n".join(
                [f"- {v['id']}: {v['description']}" for v in violations]
            )
            self.fail(f"Screen reader compatibility issues found:\n{violation_details}")

    def test_color_contrast(self):
        """Test that text and UI elements have sufficient color contrast."""
        self._login()
        self.driver.get(f"{self.live_server_url}/admin/translations/")

        # Run color contrast checks
        results = self._run_axe(
            options={"runOnly": {"type": "tag", "values": ["cat.color"]}}
        )

        violations = results["violations"]

        if violations:
            contrast_issues = "\n".join(
                [
                    f"- {v['id']}: {v['description']} (Impact: {v.get('impact', 'unknown')})"
                    for v in violations
                ]
            )
            self.fail(f"Color contrast violations:\n{contrast_issues}")

    def test_table_accessibility(self):
        """Test that the dashboard table is accessible."""
        self._login()
        self.driver.get(f"{self.live_server_url}/admin/translations/")

        # Run tests specific to tables
        results = self._run_axe(
            options={"runOnly": {"type": "tag", "values": ["tables"]}}
        )

        violations = results["violations"]

        if violations:
            table_issues = "\n".join(
                [f"- {v['id']}: {v['description']}" for v in violations]
            )
            self.fail(f"Table accessibility violations:\n{table_issues}")

    def test_form_accessibility(self):
        """Test that filter form controls are accessible."""
        self._login()
        self.driver.get(f"{self.live_server_url}/admin/translations/")

        # Run tests specific to forms
        results = self._run_axe(
            options={"runOnly": {"type": "tag", "values": ["forms"]}}
        )

        violations = [
            v for v in results["violations"] if v["impact"] in ("critical", "serious")
        ]

        if violations:
            form_issues = "\n".join(
                [f"- {v['id']}: {v['description']}" for v in violations]
            )
            self.fail(f"Form accessibility violations:\n{form_issues}")

    def test_landmarks_and_regions(self):
        """Test that page has proper landmark regions for navigation."""
        self._login()
        self.driver.get(f"{self.live_server_url}/admin/translations/")

        # Run tests for landmarks and page structure
        results = self._run_axe(
            options={"runOnly": {"type": "tag", "values": ["region"]}}
        )

        violations = results["violations"]

        if violations:
            landmark_issues = "\n".join(
                [f"- {v['id']}: {v['description']}" for v in violations]
            )
            self.fail(f"Landmark/region violations:\n{landmark_issues}")

    def test_language_attributes(self):
        """Test that HTML language attributes are properly set."""
        self._login()
        self.driver.get(f"{self.live_server_url}/admin/translations/")

        # Check language-related accessibility
        results = self._run_axe(
            options={"runOnly": {"type": "tag", "values": ["language"]}}
        )

        violations = results["violations"]

        assert len(violations) == 0, f"Language attribute violations:\n{violations}"

    def test_empty_dashboard_accessibility(self):
        """Test accessibility when dashboard has no data."""
        # Clear all translation progress records
        TranslationProgress.objects.all().delete()

        self._login()
        self.driver.get(f"{self.live_server_url}/admin/translations/")

        # Run comprehensive accessibility check on empty state
        results = self._run_axe()

        violations = [
            v for v in results["violations"] if v["impact"] in ("critical", "serious")
        ]

        if violations:
            violation_details = "\n".join(
                [f"- {v['id']}: {v['description']}" for v in violations]
            )
            self.fail(
                f"Accessibility violations in empty dashboard state:\n{violation_details}"
            )

    def test_filtered_dashboard_accessibility(self):
        """Test accessibility when filters are applied."""
        self._login()

        # Apply filters via URL parameters
        self.driver.get(
            f"{self.live_server_url}/admin/translations/?search=test&original_language=en"
        )

        # Run accessibility check on filtered state
        results = self._run_axe()

        violations = [
            v for v in results["violations"] if v["impact"] in ("critical", "serious")
        ]

        if violations:
            violation_details = "\n".join(
                [f"- {v['id']}: {v['description']}" for v in violations]
            )
            self.fail(
                f"Accessibility violations in filtered dashboard:\n{violation_details}"
            )
