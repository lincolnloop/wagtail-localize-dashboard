"""Models for storing cached translation progress data."""

from typing import Any, Dict

from django.db import models
from django.urls import reverse

from wagtail.models import Page


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
        help_text="The original source page",
    )

    # Translated page (in a specific locale)
    translated_page = models.ForeignKey(
        Page,
        on_delete=models.CASCADE,
        related_name="translation_progress_translated",
        db_index=True,
        help_text="The translated page",
    )

    # Translation progress (0-100)
    percent_translated = models.IntegerField(
        default=0, help_text="Percentage of segments translated (0-100)"
    )

    # Metadata
    last_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Translation Progress"
        verbose_name_plural = "Translation Progress"

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
