"""Signal handlers for automatic cache updates."""

import logging
from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver
from wagtail.models import Page
from wagtail_localize.models import (
    StringSegment,
    StringTranslation,
    Translation,
    TranslationLog,
    TranslationSource,
)

from .models import SnippetTranslationProgress
from .settings import get_setting, get_tracked_snippet_models
from .utils import create_page_translation_progress, create_snippet_translation_progress

logger = logging.getLogger(__name__)


def should_auto_update() -> bool:
    """Check if auto-update is enabled."""
    return get_setting("ENABLED") and get_setting("AUTO_UPDATE")


def noop_timestamps_are_preserved() -> bool:
    """Return whether a no-op StringTranslation save should keep its timestamp."""
    return get_setting("ENABLED") and get_setting("PRESERVE_TIMESTAMP_ON_NOOP_SAVES")


@receiver(pre_save, sender=StringTranslation)
def remember_previous_stringtranslation(
    sender: type, instance: StringTranslation, **kwargs: Any
) -> None:
    """Stash the stored row so post_save can tell a real edit from a no-op."""
    instance._dashboard_previous_translation = None
    if (
        kwargs.get("raw", False)
        or not noop_timestamps_are_preserved()
        or not instance.pk
    ):
        return
    try:
        instance._dashboard_previous_translation = (
            StringTranslation.objects.using(kwargs.get("using"))
            .filter(pk=instance.pk)
            .values("data", "has_error", "updated_at")
            .first()
        )
    except Exception:
        # Never let this package's bookkeeping break somebody else's save.
        logger.exception("Error in remember_previous_stringtranslation")
        instance._dashboard_previous_translation = None


@receiver(post_save, sender=StringTranslation)
def restore_updated_stringtranslation_at_on_noop(
    sender: type, instance: StringTranslation, created: bool, **kwargs: Any
) -> None:
    """Put updated_at back when a save changed nothing that reaches the target.

    percent_published asks whether a translation was last written before the
    last push. wagtail-localize's segment editor writes unconditionally, so a
    translator who opens a segment and saves without typing would otherwise
    drop that segment out of the published count and make a fully live page
    look stale.

    Only data and has_error are compared, because those are the only fields
    _count_published() reads. The editor also always sends last_translated_by
    and resets tool_name; neither changes what is on the target, so both are
    ignored on purpose.

    One no-op is deliberately NOT suppressed: a byte-identical re-save of a row
    stored with has_error=True. The editor always posts has_error=False and
    lets StringTranslation.save() re-derive it, so the comparison below sees
    True != False and lets the bump stand. Harmless - errored segments never
    count as published, so the percentage does not move either way.

    queryset.update() is deliberate: it bypasses field pre_save(), so it can
    write a value auto_now would otherwise overwrite. It also fires no signals,
    so this cannot recurse.
    """
    previous = getattr(instance, "_dashboard_previous_translation", None)
    if created or kwargs.get("raw", False) or not previous:
        return
    if previous["data"] != instance.data or previous["has_error"] != instance.has_error:
        return

    if previous["updated_at"] == instance.updated_at:
        return

    try:
        StringTranslation.objects.using(kwargs.get("using")).filter(
            pk=instance.pk
        ).update(updated_at=previous["updated_at"])
    except Exception:
        # Never let this package's bookkeeping break somebody else's save.
        logger.exception("Error in restore_updated_stringtranslation_at_on_noop")
        return

    instance.updated_at = previous["updated_at"]
    logger.debug(
        "Preserved updated_at at %s for StringTranslation %s after a no-op save",
        previous["updated_at"],
        instance.pk,
    )


class _PageTranslationProgressRebuild:
    """One pending rebuild of a page's progress, queued until commit."""

    __slots__ = ("locale_id", "saved_pk", "translation_key")

    def __init__(
        self,
        translation_key: Any,
        locale_id: int | None,
        saved_pk: int | None = None,
    ) -> None:
        self.translation_key = translation_key
        self.locale_id = locale_id
        self.saved_pk = saved_pk

    @property
    def key(self) -> tuple[Any, int | None, int | None]:
        return (self.translation_key, self.locale_id, self.saved_pk)

    def __call__(self) -> None:
        try:
            original_page = (
                Page.objects.filter(translation_key=self.translation_key)
                .order_by("id")
                .first()
            )
            if original_page is None:
                return

            only_locale = self.locale_id
            # If the saved_pk is the original_page's pk, then we set only_locale
            # to None, so all translations' progress percentages get computed.
            if self.saved_pk is not None and original_page.pk == self.saved_pk:
                only_locale = None

            create_page_translation_progress(original_page, only_locale=only_locale)
        except Exception:
            logger.exception("Error in _PageTranslationProgressRebuild %r", (self.key,))


def _queue_page_translation_progress_rebuild(
    translation_key: Any, locale_id: int | None, saved_pk: int | None = None
) -> None:
    """Queue a page rebuild to run when the current transaction commits."""
    transaction.on_commit(
        _PageTranslationProgressRebuild(translation_key, locale_id, saved_pk)
    )


def _get_source_instance_for_string_translation(
    instance: StringTranslation,
) -> Any | None:
    """The object a StringTranslation belongs to, or None if its segment is gone."""
    # We use filter().first(), rather than get(), since a rich text field that
    # repeats a phrase produces two segments sharing a (string, context) pair.
    segment = (
        StringSegment.objects.filter(
            context=instance.context, string=instance.translation_of
        )
        .order_by("order")
        .first()
    )
    if segment is None:
        return None
    return segment.source.get_source_instance()


def _rebuild_progress_for_source(source_instance: Any, locale_id: int | None) -> None:
    """Queue a progress rebuild for whichever kind of object this is."""
    if isinstance(source_instance, Page):
        if not get_setting("TRACK_PAGES"):
            return
        _queue_page_translation_progress_rebuild(
            source_instance.translation_key, locale_id
        )
        return

    if not isinstance(source_instance, tuple(get_tracked_snippet_models())):
        return

    original = (
        type(source_instance)
        .objects.filter(translation_key=source_instance.translation_key)
        .order_by("id")
        .first()
    )
    if original is None:
        return

    transaction.on_commit(
        lambda: create_snippet_translation_progress(original, only_locale=locale_id)
    )


@receiver(post_save, sender=Translation)
def translation_saved_handler(
    sender: type, instance: Translation, created: bool, **kwargs: Any
) -> None:
    """Update progress when a Translation is saved."""
    if not should_auto_update():
        return

    try:
        _rebuild_progress_for_source(
            instance.source.get_source_instance(), instance.target_locale_id
        )
    except Exception:
        logger.exception("Error in translation_saved_handler")


@receiver(post_save, sender=StringTranslation)
def string_translation_saved_handler(
    sender: type, instance: StringTranslation, created: bool, **kwargs: Any
) -> None:
    """Update progress when a StringTranslation is saved."""
    if not should_auto_update():
        return

    try:
        source_instance = _get_source_instance_for_string_translation(instance)
        if source_instance is None:
            return
        _rebuild_progress_for_source(source_instance, instance.locale_id)
    except Exception:
        logger.exception("Error in string_translation_saved_handler")


@receiver(pre_delete, sender=StringTranslation)
def string_translation_deleted_handler(
    sender: type, instance: StringTranslation, **kwargs: Any
) -> None:
    """Update progress when a StringTranslation is deleted."""
    if not should_auto_update():
        return

    try:
        source_instance = _get_source_instance_for_string_translation(instance)
        if source_instance is None:
            return
        # We get the locale now, rather than after the commit, because this row
        # will no longer exist then.
        _rebuild_progress_for_source(source_instance, instance.locale_id)
    except Exception:
        logger.exception("Error in string_translation_deleted_handler")


@receiver(post_save, sender=TranslationLog)
def translation_log_saved_handler(
    sender: type, instance: TranslationLog, created: bool, **kwargs: Any
) -> None:
    """Update progress when translations are pushed to a target.

    TranslationLog is created after create_or_update_translation's atomic block
    exits, which is after every on_commit callback queued inside it has already
    run. Without this receiver, the rebuilds triggered by a push all observe an
    empty TranslationLog and store percent_published = 0.
    """
    if not should_auto_update():
        return

    try:
        _rebuild_progress_for_source(
            instance.source.get_source_instance(), instance.locale_id
        )
    except Exception:
        logger.exception("Error in translation_log_saved_handler")


@receiver(post_save, sender=TranslationSource)
def translation_source_saved_handler(
    sender: type, instance: TranslationSource, created: bool, **kwargs: Any
) -> None:
    """Update progress when a TranslationSource is saved."""
    if not should_auto_update():
        return

    try:
        # An update to a source triggers rebuilding the progress for each locale.
        _rebuild_progress_for_source(instance.get_source_instance(), None)
    except Exception:
        logger.exception("Error in translation_source_saved_handler")


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

    _queue_page_translation_progress_rebuild(
        instance.translation_key, instance.locale_id, saved_pk=instance.pk
    )


def snippet_saved_handler(
    sender: type, instance: Any, created: bool, **kwargs: Any
) -> None:
    """
    Update snippet translation progress when a tracked snippet is saved.

    Connected to each tracked model individually in apps.py ready(), not as a
    global post_save catch-all.
    """
    if not should_auto_update():
        return

    if kwargs.get("raw", False):
        return

    def update_after_commit() -> None:
        try:
            original = (
                type(instance)
                .objects.filter(translation_key=instance.translation_key)
                .order_by("id")
                .first()
            )
            if original:
                create_snippet_translation_progress(original)
        except Exception:
            logger.exception("Error in snippet_saved_handler")

    transaction.on_commit(update_after_commit)


def snippet_deleted_handler(sender: type, instance: Any, **kwargs: Any) -> None:
    """
    Remove snippet translation progress records when a tracked snippet is deleted.

    Handles the cascade that GenericForeignKey does not do automatically.
    Connected to each tracked model individually in apps.py ready().
    """
    from django.db import models as django_models

    try:
        content_type = ContentType.objects.get_for_model(instance)
        SnippetTranslationProgress.objects.filter(
            content_type=content_type,
        ).filter(
            django_models.Q(source_object_id=instance.pk)
            | django_models.Q(translated_object_id=instance.pk)
        ).delete()
    except Exception:
        logger.exception("Error in snippet_deleted_handler")
