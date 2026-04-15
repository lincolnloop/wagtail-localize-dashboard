"""Models for storing cached translation progress data."""

from typing import Any, Dict, Optional

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from wagtail.models import DraftStateMixin, Locale, Page


class TranslationProgress(models.Model):
    """
    Stores pre-calculated translation progress for Page translations.

    This is a cache table - data is rebuilt automatically via signals
    when translations change.
    """

    # Source page (the original, typically in the default locale)
    source_page = models.ForeignKey(
        Page,
        on_delete=models.CASCADE,
        related_name="translation_progress_source",
        db_index=True,
        help_text=_("The original source page"),
    )

    # Translated page (in a specific locale)
    translated_page = models.ForeignKey(
        Page,
        on_delete=models.CASCADE,
        related_name="translation_progress_translated",
        db_index=True,
        help_text=_("The translated page"),
    )

    # Translation progress (0-100)
    percent_translated = models.IntegerField(
        default=0, help_text=_("Percentage of segments translated (0-100)")
    )

    # Metadata
    last_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Translation Progress")
        verbose_name_plural = _("Translation Progress")

        # Ensure one progress record per source-target pair
        unique_together = [["source_page", "translated_page"]]

        # Indexes for common queries
        indexes = [
            models.Index(fields=["percent_translated"], name="trans_prog_percent_idx"),
            models.Index(fields=["last_updated"], name="trans_prog_updated_idx"),
        ]

        # Default ordering
        ordering = ["-last_updated"]

    def __str__(self) -> str:
        """String representation."""
        return (
            f"{self.source_page} -> {self.translated_page} ({self.percent_translated}%)"
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Return dictionary representation for API/templates.

        Returns:
            dict with translation progress data

        Note: Expects translated_page.locale to be prefetched via select_related()
        """
        # Access locale from the translated_page (should be prefetched)
        try:
            locale = self.translated_page.locale.language_code
        except AttributeError:
            locale = "unknown"

        try:
            edit_url = self.get_edit_url()
        except Exception:
            edit_url = "#"

        return {
            "locale": locale,
            "percent_translated": self.percent_translated,
            "edit_url": edit_url,
            "view_url": self.get_view_url,
            "last_updated": self.last_updated,
            "live": self.translated_page.live,
            "has_unpublished_changes": self.translated_page.has_unpublished_changes,
        }

    def get_edit_url(self) -> str:
        """
        Get the edit URL for the translated page.

        Returns:
            str: URL to edit the translated page in Wagtail admin
        """
        return reverse("wagtailadmin_pages:edit", args=[self.translated_page_id])

    @property
    def get_view_url(self) -> str:
        """Get view URL for the translated page."""
        if hasattr(self.translated_page, "get_url"):
            return self.translated_page.get_url()
        return ""


class SnippetTranslationProgress(models.Model):
    """
    Stores pre-calculated translation progress for snippet translations.

    A single content_type field covers both source and translated objects because
    snippet translations are always same-type pairs (a NavigationMenu translates
    into a NavigationMenu, never a different model).

    This is a cache table - data is rebuilt automatically via signals
    when translations change.
    """

    # Shared content type for both source and translated snippet
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        db_index=True,
        help_text=_("The content type shared by source and translated snippet"),
    )

    # Source snippet (the original, typically in the default locale)
    source_object_id = models.PositiveIntegerField(
        db_index=True,
        help_text=_("The primary key of the source snippet"),
    )
    source = GenericForeignKey("content_type", "source_object_id")

    # Translated snippet (in a specific locale)
    translated_object_id = models.PositiveIntegerField(
        db_index=True,
        help_text=_("The primary key of the translated snippet"),
    )
    translated = GenericForeignKey("content_type", "translated_object_id")

    # Stored explicitly so locale can be retrieved via select_related without
    # fetching the full translated object.
    translated_locale = models.ForeignKey(
        Locale,
        on_delete=models.CASCADE,
        related_name="snippet_translation_progress",
        help_text=_("The locale of the translated snippet"),
    )

    # Translation progress (0-100)
    percent_translated = models.IntegerField(
        default=0, help_text=_("Percentage of segments translated (0-100)")
    )

    # Metadata
    last_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Snippet Translation Progress")
        verbose_name_plural = _("Snippet Translation Progress")

        unique_together = [["content_type", "source_object_id", "translated_object_id"]]

        indexes = [
            models.Index(fields=["percent_translated"], name="snip_prog_percent_idx"),
            models.Index(fields=["last_updated"], name="snip_prog_updated_idx"),
        ]

        ordering = ["-last_updated"]

    def __str__(self) -> str:
        return (
            f"{self.content_type} #{self.source_object_id}"
            f" -> #{self.translated_object_id} ({self.percent_translated}%)"
        )

    def get_edit_url(self) -> str:
        """
        Build the Wagtail snippet edit URL for the translated object.

        Uses content_type (real FK) and translated_object_id — no object
        instance needed, so this works without prefetching the translated GFK.
        """
        app_label = self.content_type.app_label
        model_name = self.content_type.model  # already lowercase
        url_name = f"wagtailsnippets_{app_label}_{model_name}:edit"
        return reverse(url_name, args=[self.translated_object_id])

    def to_dict(self) -> Dict[str, Any]:
        """
        Return dictionary representation for use in templates.

        Expects:
          - translated_locale to be prefetched via select_related()
          - translated GFK to be prefetched via prefetch_related() when the
            snippet model uses DraftStateMixin (checked at the class level first)
        """
        locale = self.translated_locale.language_code

        try:
            edit_url = self.get_edit_url()
        except Exception:
            edit_url = "#"

        model_class = self.content_type.model_class()
        has_draft_state = model_class is not None and issubclass(
            model_class, DraftStateMixin
        )

        live: Optional[bool] = None
        has_unpublished_changes: Optional[bool] = None
        if has_draft_state:
            live = self.translated.live
            has_unpublished_changes = self.translated.has_unpublished_changes

        return {
            "locale": locale,
            "percent_translated": self.percent_translated,
            "edit_url": edit_url,
            "last_updated": self.last_updated,
            "live": live,
            "has_unpublished_changes": has_unpublished_changes,
        }
