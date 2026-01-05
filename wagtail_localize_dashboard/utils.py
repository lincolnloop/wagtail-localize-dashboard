"""Utility functions for calculating and managing translation progress."""

import logging
from typing import Dict, Optional

from django.db.models import Min, Model, QuerySet

from wagtail.models import Locale, Page
from wagtail_localize.models import TranslatableObject, Translation, TranslationSource

from .models import TranslationProgress
from .settings import get_setting

logger = logging.getLogger(__name__)


def get_translation_percentages(
    source_page: Page, target_locale: Locale
) -> Optional[int]:
    """
    Calculate translation percentage for a source page to target locale.

    Args:
        source_page: The source Page object
        target_locale: The target Locale instance

    Returns:
        int: Percentage translated (0-100), or None if no translation exists

    Example:
        >>> from wagtail.models import Locale
        >>> page = Page.objects.get(id=123)
        >>> locale_de = Locale.objects.get(language_code="de")
        >>> percent = get_translation_percentages(page, locale_de)
        >>> print(f"{percent}% translated")
    """
    try:
        # Find the translation source for the source page
        translation_source = TranslationSource.objects.get_for_instance(source_page)

        # Find the Translation record for this locale
        translation_record = Translation.objects.get(
            source=translation_source, target_locale=target_locale
        )

        # Get the actual translation progress using wagtail-localize logic
        total_segments, translated_segments = translation_record.get_progress()

        if total_segments > 0:
            percent_translated = int(translated_segments / total_segments * 100)
        else:
            percent_translated = 100  # No segments = 100% complete

        return percent_translated

    except (
        TranslationSource.DoesNotExist,
        Translation.DoesNotExist,
        TranslatableObject.DoesNotExist,
    ):
        return None


def create_translation_progress(source_page: Page) -> None:
    """
    Calculate and store translation progress for a source page.

    Creates or updates TranslationProgress records for all translations
    of the given source page.

    Args:
        source_page: The source Page object

    Example:
        >>> page = Page.objects.get(id=123)
        >>> create_translation_progress(page)
    """
    # Check if tracking is enabled
    if not get_setting("TRACK_PAGES"):
        return

    try:
        # Get all translations of this page
        translations = source_page.get_translations()

        # Loop over all translations
        for translated_page in translations:
            # Skip if same as source
            if translated_page.id == source_page.id:
                continue

            # Try to get translation percentage from source to this translation
            percent_translated = get_translation_percentages(
                source_page, translated_page.locale
            )

            # If we can't get data from source to translation,
            # the translation might be a translation of another translation.
            # Try other translations as sources.
            if percent_translated is None:
                for other_translation in translations:
                    if other_translation.id == translated_page.id:
                        continue

                    percent_translated = get_translation_percentages(
                        other_translation, translated_page.locale
                    )

                    if percent_translated is not None:
                        break

            # Create or update progress record
            TranslationProgress.objects.update_or_create(
                source_page=source_page,
                translated_page=translated_page,
                defaults={
                    "percent_translated": percent_translated or 0,
                },
            )

    except (ValueError, AttributeError) as error:
        # If there's an unexpected error, log it
        logger.exception(
            f"Error creating translation progress for {source_page}: {error}",
            stack_info=True,
        )


def rebuild_all_progress() -> Dict[str, int]:
    """
    Rebuild translation progress for all pages.

    This is useful for:
    - Initial setup
    - After bulk imports
    - Fixing inconsistencies

    Returns:
        dict with counts of processed pages and errors

    Example:
        >>> stats = rebuild_all_progress()
        >>> print(f"Processed {stats['pages']} pages")
    """
    stats = {
        "pages": 0,
        "errors": 0,
    }

    # Process pages
    if get_setting("TRACK_PAGES"):
        original_pages = get_original_objects(Page)

        for page in original_pages:
            try:
                create_translation_progress(page)
                stats["pages"] += 1
            except Exception as e:
                logger.exception(f"Error processing page {page.id}: {e}")
                stats["errors"] += 1

    return stats


def get_original_objects(model: type[Model]) -> QuerySet:
    """
    Get original objects for a model (min ID per translation_key).

    Args:
        model: Django model class

    Returns:
        QuerySet of original objects
    """
    all_objects = model.objects.all()

    # For Pages, filter out root pages (depth <= 2)
    if issubclass(model, Page):
        all_objects = all_objects.filter(depth__gt=2)

    if not hasattr(model, "translation_key"):
        return all_objects

    # Get min ID per translation key
    original_ids = (
        all_objects.order_by("translation_key")
        .values("translation_key")
        .annotate(min_id=Min("id"))
        .values_list("min_id", flat=True)
    )

    return model.objects.filter(id__in=original_ids)
