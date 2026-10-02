"""Utility functions for calculating and managing translation progress."""

import logging

from django.contrib.contenttypes.models import ContentType
from django.db.models import Exists, Max, Min, Model, OuterRef, QuerySet
from wagtail.models import DraftStateMixin, Locale, Page
from wagtail_localize.models import (
    StringSegment,
    StringTranslation,
    TranslatableObject,
    Translation,
    TranslationLog,
    TranslationSource,
)

from .models import SnippetTranslationProgress, TranslationProgress
from .settings import get_setting, get_tracked_snippet_models

logger = logging.getLogger(__name__)


def get_translation_percentages(
    source_object: Model, target_locale: Locale
) -> int | None:
    """
    Calculate translation percentage for a source object to target locale.

    Works for any TranslatableMixin model (pages and snippets alike).

    Args:
        source_object: The source model instance (Page or any translatable snippet)
        target_locale: The target Locale instance

    Returns:
        int: Percentage translated (0-100), or None if no translation exists

    Example:
        >>> from wagtail.models import Locale
        >>> page = Page.objects.get(id=123)
        >>> locale_de = Locale.objects.get(language_code="de")
        >>> percent = get_translation_percentages(page, locale_de)
        >>> print(f"{percent}% translated")

    Note:
        Retained as public API. The dashboard itself now uses
        get_translation_progress(), which returns this figure plus the published
        percentage.
    """
    try:
        # Find the translation source for the source object
        translation_source = TranslationSource.objects.get_for_instance(source_object)

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


def _count_published(
    source: TranslationSource,
    target_locale: Locale,
    translated_object: Model | None,
) -> int:
    """
    Count segments whose translations are live on the target.

    This mirrors Translation.get_progress(): it annotates StringSegment rows
    with an Exists() over StringTranslation joined on the pair
    (string_id, context_id) and counts *segments*. The only addition is the
    updated_at bound. Counting StringTranslation rows instead - for example via
    StringSegmentQuerySet.get_translations() - undercounts, because a rich text
    field holding the same phrase twice produces two segments that share one
    (string, context) pair and therefore one StringTranslation.

    What the timestamp bound means
    ------------------------------
    updated_at__lte=last_push answers "was this translation last written before
    the last push", NOT "was this translation included in the last push".
    Upstream records no per-segment push provenance, so this is the closest
    available proxy. StringTranslation.updated_at is auto_now=True, which gives
    the proxy two known errors:

    - False gap. The edit_string_translation view does an unconditional
      update_or_create, so re-saving a segment with BYTE-IDENTICAL text bumps
      updated_at and drops that segment out of the published count. It errs
      safe (it under-reports published, never over-reports), but a translator
      who opens a segment and saves without editing will see a gap appear and
      will report it as a bug.
    - False publish. A segment removed from the source and re-added after a
      push keeps its old StringTranslation row, and therefore its old
      updated_at, so it counts as published even though it was never pushed.

    Do not "fix" either by switching to last_published_at.

    Args:
        source: The TranslationSource for the source object
        target_locale: The target Locale instance
        translated_object: The translated instance, or None when the caller has
            none. Required, not defaulted: passing None skips the live gate.

    Returns:
        int: Number of segments whose translation was live as of the last push
    """
    # Nothing is on display if the target isn't live, whatever was pushed.
    if isinstance(translated_object, DraftStateMixin) and not translated_object.live:
        return 0

    # TranslationLog records every save_target(); its latest entry is the last
    # time translations were written into the target. last_published_at is not
    # equivalent - publishing the target by any other route bumps it without
    # pushing anything.
    last_push = TranslationLog.objects.filter(
        source=source, locale=target_locale
    ).aggregate(at=Max("created_at"))["at"]

    if last_push is None:
        return 0

    return (
        StringSegment.objects.filter(source=source)
        .annotate(
            is_published=Exists(
                StringTranslation.objects.filter(
                    translation_of_id=OuterRef("string_id"),
                    context_id=OuterRef("context_id"),
                    locale_id=target_locale.pk,
                    has_error=False,
                    updated_at__lte=last_push,
                )
            )
        )
        .filter(is_published=True)
        .count()
    )


def get_translation_progress(
    source_object: Model,
    target_locale: Locale,
    translated_object: Model | None,
) -> tuple[int, int, bool] | None:
    """
    Calculate translated and published percentages for a source/locale pair.

    percent_translated is wagtail-localize's own figure, untouched.
    percent_published is the share of segments whose translations have actually
    been pushed to a live target.

    Args:
        source_object: The source model instance (Page or translatable snippet)
        target_locale: The target Locale instance
        translated_object: The translated instance, or None. Required - without
            it the live gate cannot run and every target looks published.

    Returns:
        tuple[int, int, bool]: (percent_translated, percent_published,
            has_unpublished_translations), or None if no translation exists.

    Example:
        >>> get_translation_progress(page, locale_de, translated_page)
        (60, 40, True)
    """
    try:
        source = TranslationSource.objects.get_for_instance(source_object)
        translation = Translation.objects.get(
            source=source, target_locale=target_locale
        )
    except (
        TranslationSource.DoesNotExist,
        Translation.DoesNotExist,
        TranslatableObject.DoesNotExist,
    ):
        return None

    total_segments, translated_segments = translation.get_progress()

    # With nothing to translate there is nothing that could be unpublished,
    # so an unpublished empty target still reports (100, 100). Otherwise, a
    # target with no translatable text looks 0% live forever.
    if total_segments == 0:
        return 100, 100, False

    percent_translated = int(translated_segments / total_segments * 100)
    published_segments = _count_published(source, target_locale, translated_object)
    percent_published = int(published_segments / total_segments * 100)

    # Compare the raw counts since int() truncation can make rounded
    # percentages equivalent despite raw percentages being unequal.
    has_unpublished_translations = published_segments < translated_segments

    # Published can never outrank translated, whatever upstream's definitions do
    return (
        percent_translated,
        min(percent_published, percent_translated),
        has_unpublished_translations,
    )


def create_page_translation_progress(source_page: Page) -> None:
    """
    Calculate and store translation progress for a source page.

    Creates or updates TranslationProgress records for all translations
    of the given source page.

    Args:
        source_page: The source Page object

    Example:
        >>> page = Page.objects.get(id=123)
        >>> create_page_translation_progress(page)
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

            # Try to get progress from source to this translation
            progress = get_translation_progress(
                source_page, translated_page.locale, translated_page
            )

            # If we can't get data from source to translation,
            # the translation might be a translation of another translation.
            # Try other translations as sources.
            if progress is None:
                for other_translation in translations:
                    if other_translation.id == translated_page.id:
                        continue

                    progress = get_translation_progress(
                        other_translation, translated_page.locale, translated_page
                    )

                    if progress is not None:
                        break

            percent_translated, percent_published, has_unpublished = progress or (
                0,
                None,
                False,
            )

            # Create or update progress record
            TranslationProgress.objects.update_or_create(
                source_page=source_page,
                translated_page=translated_page,
                defaults={
                    "percent_translated": percent_translated,
                    "percent_published": percent_published,
                    "has_unpublished_translations": has_unpublished,
                },
            )

    except (ValueError, AttributeError):
        # If there's an unexpected error, log it
        logger.exception(
            f"Error creating translation progress for {source_page}",
            stack_info=True,
        )


def rebuild_all_progress_for_pages() -> dict[str, int]:
    """
    Rebuild translation progress for all pages.

    This is useful for:
    - Initial setup
    - After bulk imports
    - Fixing inconsistencies

    Returns:
        dict with counts of processed pages and errors

    Example:
        >>> stats = rebuild_all_progress_for_pages()
        >>> print(f"Processed {stats['pages']} pages")
    """
    stats = {
        "pages": 0,
        "errors": 0,
    }

    if get_setting("TRACK_PAGES"):
        original_pages = get_original_objects(Page)

        for page in original_pages:
            try:
                create_page_translation_progress(page)
                stats["pages"] += 1
            except Exception:
                logger.exception(f"Error processing page {page.id}")
                stats["errors"] += 1

    return stats


def create_snippet_translation_progress(source_snippet: Model) -> None:
    """
    Calculate and store translation progress for a source snippet.

    Creates or updates SnippetTranslationProgress records for all translations
    of the given source snippet.

    Args:
        source_snippet: The source snippet instance (must be TranslatableMixin)
    """
    try:
        content_type = ContentType.objects.get_for_model(source_snippet)
        translations = source_snippet.get_translations()

        for translated_snippet in translations:
            if translated_snippet.pk == source_snippet.pk:
                continue

            progress = get_translation_progress(
                source_snippet, translated_snippet.locale, translated_snippet
            )

            if progress is None:
                for other_translation in translations:
                    if other_translation.pk == translated_snippet.pk:
                        continue
                    progress = get_translation_progress(
                        other_translation, translated_snippet.locale, translated_snippet
                    )
                    if progress is not None:
                        break

            percent_translated, percent_published, has_unpublished = progress or (
                0,
                None,
                False,
            )

            SnippetTranslationProgress.objects.update_or_create(
                content_type=content_type,
                source_object_id=source_snippet.pk,
                translated_object_id=translated_snippet.pk,
                defaults={
                    "translated_locale": translated_snippet.locale,
                    "percent_translated": percent_translated,
                    "percent_published": percent_published,
                    "has_unpublished_translations": has_unpublished,
                },
            )

    except (ValueError, AttributeError):
        logger.exception(
            f"Error creating snippet translation progress for {source_snippet}",
            stack_info=True,
        )


def rebuild_all_snippet_progress() -> dict[str, int]:
    """
    Rebuild translation progress for all tracked snippets.

    Returns:
        dict with counts of processed snippets and errors
    """
    stats = {
        "snippets": 0,
        "errors": 0,
    }

    for model in get_tracked_snippet_models():
        for snippet in get_original_objects(model):
            try:
                create_snippet_translation_progress(snippet)
                stats["snippets"] += 1
            except Exception:
                logger.exception(f"Error processing snippet {snippet}")
                stats["errors"] += 1

    return stats


def rebuild_all_progress() -> dict[str, int]:
    """
    Rebuild translation progress for all pages and all tracked snippets.

    Returns:
        dict with combined counts of processed pages, snippets, and errors

    Example:
        >>> stats = rebuild_all_progress()
        >>> print(f"Processed {stats['pages']} pages, {stats['snippets']} snippets")
    """
    page_stats = rebuild_all_progress_for_pages()
    snippet_stats = rebuild_all_snippet_progress()
    return {
        "pages": page_stats["pages"],
        "snippets": snippet_stats["snippets"],
        "errors": page_stats["errors"] + snippet_stats["errors"],
    }


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
