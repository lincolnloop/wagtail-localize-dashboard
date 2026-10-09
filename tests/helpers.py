"""Shared helpers for tests that publish and re-save translations."""

from unittest.mock import patch

from django.db import transaction
from wagtail_localize.models import (
    StringSegment,
    StringTranslation,
    Translation,
    TranslationSource,
)

# Ensure save_target() actually publishes, since wagtail-localize defers
# publishing to transaction.on_commit().
run_on_commit = patch.object(transaction, "on_commit", side_effect=lambda func: func())


def translate_all_segments_and_publish(source_object, locale):
    """Translate every segment of source_object into locale and push it live."""
    source, __ = TranslationSource.get_or_create_from_instance(source_object)
    translation, __ = Translation.objects.get_or_create(
        source=source, target_locale=locale
    )
    for segment in StringSegment.objects.filter(source=source).order_by("order"):
        StringTranslation.objects.update_or_create(
            translation_of=segment.string,
            context=segment.context,
            locale=locale,
            defaults={"data": f"DE {segment.context.path}"},
        )
    translation.save_target(publish=True)
    return source, translation


def get_first_segment_translation(source, locale):
    """Return the StringTranslation for the first segment of source."""
    segment = StringSegment.objects.filter(source=source).order_by("order").first()
    return StringTranslation.objects.get(
        translation_of=segment.string, context=segment.context, locale=locale
    )


def resave_first_segment_like_editor(
    source, locale, data=None, has_error=False, user=None
):
    """Repeat the write wagtail-localize's segment editor does."""
    stored = get_first_segment_translation(source, locale)
    StringTranslation.objects.update_or_create(
        translation_of_id=stored.translation_of_id,
        locale_id=locale.pk,
        context_id=stored.context_id,
        defaults={
            "data": stored.data if data is None else data,
            "translation_type": StringTranslation.TRANSLATION_TYPE_MANUAL,
            "tool_name": "",
            "last_translated_by": user,
            "has_error": has_error,
            "field_error": "",
        },
    )


def target_of(source_object, locale):
    """The translated instance of source_object in locale."""
    return type(source_object).objects.get(
        translation_key=source_object.translation_key, locale=locale
    )
