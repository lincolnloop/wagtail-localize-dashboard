import pytest
from django.db import transaction

from wagtail_localize_dashboard.signals import _PageTranslationProgressRebuild

pytestmark = [pytest.mark.django_db]


def test_fixture_setup_leaves_no_pending_rebuilds(test_page):
    """Saving pages in a fixture must not leave rebuilds pending for the body."""
    pending = [
        entry
        for entry in transaction.get_connection().run_on_commit
        if isinstance(entry[1], _PageTranslationProgressRebuild)
    ]

    assert pending == [], (
        f"{len(pending)} rebuild(s) queued while fixtures were being built are "
        "still pending when the test body starts"
    )
