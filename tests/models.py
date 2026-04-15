"""Test models for wagtail-localize-dashboard tests."""

from django.db import models
from wagtail.models import DraftStateMixin, RevisionMixin, TranslatableMixin
from wagtail.snippets.models import register_snippet


@register_snippet
class SampleSnippet(TranslatableMixin, models.Model):
    """A simple snippet model for testing signal behavior with non-Page objects."""

    heading = models.CharField(max_length=255)
    desc = models.TextField(blank=True)

    class Meta:
        unique_together = [("translation_key", "locale")]

    def __str__(self):
        return self.heading


@register_snippet
class DraftStateSnippet(
    DraftStateMixin, RevisionMixin, TranslatableMixin, models.Model
):
    """A snippet with DraftStateMixin for testing live/draft detection."""

    title = models.CharField(max_length=255)

    class Meta:
        unique_together = [("translation_key", "locale")]

    def __str__(self):
        return self.title
