"""Signal handlers for automatic cache updates."""

import logging
from typing import Any

from django.db import transaction
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from wagtail.models import Page
from wagtail_localize.models import (
    StringSegment,
    StringTranslation,
    Translation,
    TranslationSource,
)

from .settings import get_setting
from .utils import create_translation_progress

logger = logging.getLogger(__name__)


def should_auto_update() -> bool:
    """Check if auto-update is enabled."""
    return get_setting("ENABLED") and get_setting("AUTO_UPDATE")


@receiver(post_save, sender=Translation)
def translation_saved_handler(
    sender: type, instance: Translation, created: bool, **kwargs: Any
) -> None:
    """Update progress when a Translation is saved."""
    if not should_auto_update():
        return

    def update_after_commit() -> None:
        try:
            source_instance = instance.source.get_source_instance()

            # Only track Pages
            if not isinstance(source_instance, Page):
                return

            if not get_setting("TRACK_PAGES"):
                return

            # Get the original page (min ID per translation_key)
            if hasattr(source_instance, "translation_key"):
                original_page = (
                    Page.objects.filter(translation_key=source_instance.translation_key)
                    .order_by("id")
                    .first()
                )
                if original_page:
                    create_translation_progress(original_page)
        except Exception as e:
            logger.exception(f"Error in translation_saved_handler: {e}")

    transaction.on_commit(update_after_commit)


@receiver(post_save, sender=StringTranslation)
def string_translation_saved_handler(
    sender: type, instance: StringTranslation, created: bool, **kwargs: Any
) -> None:
    """Update progress when a StringTranslation is saved."""
    if not should_auto_update():
        return

    def update_after_commit() -> None:
        try:
            # Get the page through the segments
            # StringTranslation -> StringSegment -> TranslationSource -> Page
            segment = StringSegment.objects.get(
                context=instance.context, string=instance.translation_of
            )
            source_instance = segment.source.get_source_instance()

            # Only track Pages
            if not isinstance(source_instance, Page):
                return

            if not get_setting("TRACK_PAGES"):
                return

            # Get the original page
            if hasattr(source_instance, "translation_key"):
                original_page = (
                    Page.objects.filter(translation_key=source_instance.translation_key)
                    .order_by("id")
                    .first()
                )
                if original_page:
                    create_translation_progress(original_page)
        except Exception as e:
            logger.exception(f"Error in string_translation_saved_handler: {e}")

    transaction.on_commit(update_after_commit)


@receiver(pre_delete, sender=StringTranslation)
def string_translation_deleted_handler(
    sender: type, instance: StringTranslation, **kwargs: Any
) -> None:
    """Update progress when a StringTranslation is deleted."""
    if not should_auto_update():
        return

    try:
        # Get the page before deletion
        segment = StringSegment.objects.get(
            context=instance.context, string=instance.translation_of
        )
        source_instance = segment.source.get_source_instance()

        # Only track Pages
        if not isinstance(source_instance, Page):
            return

        if not get_setting("TRACK_PAGES"):
            return

        # Get the original page
        if hasattr(source_instance, "translation_key"):
            original_page = (
                Page.objects.filter(translation_key=source_instance.translation_key)
                .order_by("id")
                .first()
            )

            def update_after_commit() -> None:
                try:
                    if original_page:
                        create_translation_progress(original_page)
                except Exception as e:
                    logger.exception(f"Error in update_after_commit: {e}")

            transaction.on_commit(update_after_commit)
    except Exception as e:
        logger.exception(f"Error in string_translation_deleted_handler: {e}")


@receiver(post_save, sender=TranslationSource)
def translation_source_saved_handler(
    sender: type, instance: TranslationSource, created: bool, **kwargs: Any
) -> None:
    """Update progress when a TranslationSource is saved."""
    if not should_auto_update():
        return

    def update_after_commit() -> None:
        try:
            source_instance = instance.get_source_instance()

            # Only track Pages
            if not isinstance(source_instance, Page):
                return

            if not get_setting("TRACK_PAGES"):
                return

            # Get the original page
            if hasattr(source_instance, "translation_key"):
                original_page = (
                    Page.objects.filter(translation_key=source_instance.translation_key)
                    .order_by("id")
                    .first()
                )
                if original_page:
                    create_translation_progress(original_page)
        except Exception as e:
            logger.exception(f"Error in translation_source_saved_handler: {e}")

    transaction.on_commit(update_after_commit)


@receiver(post_save)
def page_saved_handler(
    sender: type, instance: Any, created: bool, **kwargs: Any
) -> None:
    """Update progress when a Page is saved."""
    if not should_auto_update():
        return

    # Only process Pages
    if not isinstance(instance, Page):
        return

    # Don't process raw saves (from fixtures, migrations, etc)
    if kwargs.get("raw", False):
        return

    if not get_setting("TRACK_PAGES"):
        return

    def update_after_commit() -> None:
        try:
            # Get the original page
            original_page = (
                Page.objects.filter(translation_key=instance.translation_key)
                .order_by("id")
                .first()
            )
            if original_page:
                create_translation_progress(original_page)
        except Exception as e:
            logger.exception(f"Error in page_saved_handler: {e}")

    transaction.on_commit(update_after_commit)
