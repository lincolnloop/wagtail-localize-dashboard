"""
Pytest fixtures for wagtail-localize-dashboard tests.

These fixtures provide reusable test setup for all test files.
"""

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType

import pytest
from wagtail.models import Locale, Page, Site

User = get_user_model()


@pytest.fixture
def root_page(db):
    """Create and return the Wagtail root page."""
    try:
        return Page.objects.get(depth=1)
    except Page.DoesNotExist:
        root = Page(
            title="Root",
            slug="root",
            content_type=ContentType.objects.get_for_model(Page),
            path="0001",
            depth=1,
            numchild=0,
            url_path="/",
        )
        root.save()
        return root


@pytest.fixture
def home_page(db, root_page):
    """Create and return a home page."""
    try:
        return Page.objects.get(slug="home", depth=2)
    except Page.DoesNotExist:
        home = Page(
            title="Home",
            slug="home",
            content_type=ContentType.objects.get_for_model(Page),
            locale=Locale.objects.get_or_create(language_code="en")[0],
        )
        root_page.add_child(instance=home)

        # Create default site if it doesn't exist
        if not Site.objects.filter(is_default_site=True).exists():
            Site.objects.create(
                hostname="localhost",
                port=80,
                site_name="Test Site",
                root_page=home,
                is_default_site=True,
            )

        return home


@pytest.fixture
def locale_en(db):
    """Create and return English locale."""
    locale, _ = Locale.objects.get_or_create(language_code="en")
    return locale


@pytest.fixture
def locale_de(db):
    """Create and return German locale."""
    locale, _ = Locale.objects.get_or_create(language_code="de")
    return locale


@pytest.fixture
def locale_es(db):
    """Create and return Spanish locale."""
    locale, _ = Locale.objects.get_or_create(language_code="es")
    return locale


@pytest.fixture
def locale_fr(db):
    """Create and return French locale."""
    locale, _ = Locale.objects.get_or_create(language_code="fr")
    return locale


@pytest.fixture
def test_page(db, home_page, locale_en):
    """Create and return a test page."""
    page = Page(
        title="Test Page",
        slug="test-page",
        locale=locale_en,
        content_type=ContentType.objects.get_for_model(Page),
    )
    home_page.add_child(instance=page)
    return page


@pytest.fixture
def test_page_with_translations(db, test_page, locale_de, locale_es):
    """Create a test page with translations in multiple locales."""
    from wagtail_localize.models import Translation, TranslationSource

    # Create translation source
    translation_source, _ = TranslationSource.get_or_create_from_instance(test_page)

    # Create German translation
    translation_de, _ = Translation.objects.get_or_create(
        source=translation_source,
        target_locale=locale_de,
    )
    translation_de.save_target(publish=True)

    # Create Spanish translation
    translation_es, _ = Translation.objects.get_or_create(
        source=translation_source,
        target_locale=locale_es,
    )
    translation_es.save_target(publish=True)

    return test_page


@pytest.fixture
def admin_user(db):
    """Create and return a superuser."""
    user = User.objects.create_superuser(
        username="admin",
        email="admin@example.com",
        password="password123",
    )
    # Ensure user has is_staff set (should be set by create_superuser, but let's be explicit)
    user.is_staff = True
    user.save()
    return user


@pytest.fixture
def staff_user(db):
    """Create and return a staff user (non-superuser)."""
    return User.objects.create_user(
        username="staff",
        email="staff@example.com",
        password="password123",
        is_staff=True,
    )


@pytest.fixture
def regular_user(db):
    """Create and return a regular user (non-staff)."""
    return User.objects.create_user(
        username="user",
        email="user@example.com",
        password="password123",
    )


@pytest.fixture
def admin_client(client, admin_user):
    """Return a client logged in as admin."""
    client.force_login(admin_user)
    return client


@pytest.fixture
def staff_client(client, staff_user):
    """Return a client logged in as staff user."""
    client.force_login(staff_user)
    return client
