"""Test models for wagtail-localize-dashboard tests."""

from django.db import models
from django.utils.html import strip_tags
from wagtail.fields import RichTextField
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


@register_snippet
class RichTextSnippet(TranslatableMixin, models.Model):
    """A snippet with a RichTextField, which can yield several segments per context."""

    body = RichTextField(blank=True)

    class Meta:
        unique_together = [("translation_key", "locale")]

    def __str__(self):
        # __str__ becomes display_str and the sort key on the snippet dashboard,
        # so it must not be raw markup.
        return strip_tags(self.body)
