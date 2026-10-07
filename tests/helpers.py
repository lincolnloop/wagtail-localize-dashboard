"""Shared helpers for tests that publish and re-save translations."""

from unittest.mock import patch

from django.db import transaction

# Ensure save_target() actually publishes, since wagtail-localize defers
# publishing to transaction.on_commit().
run_on_commit = patch.object(transaction, "on_commit", side_effect=lambda func: func())


def target_of(source_object, locale):
    """The translated instance of source_object in locale."""
    return type(source_object).objects.get(
        translation_key=source_object.translation_key, locale=locale
    )
