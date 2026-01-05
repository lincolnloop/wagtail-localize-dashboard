"""Forms for filtering the translation dashboard."""

from typing import Any

from django import forms
from django.conf import settings


class ProgressFilterForm(forms.Form):
    """Filter form for the translation progress dashboard."""

    ALL_LANGUAGES = "__all__"
    CORE_LANGUAGES = "__core__"

    search = forms.CharField(
        required=False,
        label="Search",
        widget=forms.TextInput(
            attrs={
                "class": "w-field__input",
                "placeholder": "Search by title or slug...",
            }
        ),
    )

    translation_key = forms.UUIDField(
        required=False,
        label="Translation Key",
        widget=forms.TextInput(
            attrs={
                "class": "w-field__input",
                "placeholder": "Filter by translation key...",
            }
        ),
    )

    original_language = forms.ChoiceField(
        choices=[("", "Any language")] + list(settings.WAGTAIL_CONTENT_LANGUAGES),
        required=False,
        label="Original Language",
        widget=forms.Select(attrs={"class": "w-field__input"}),
    )

    exists_in_language = forms.ChoiceField(
        choices=[],  # Will be populated in __init__
        required=False,
        label="Exists In",
        widget=forms.Select(attrs={"class": "w-field__input"}),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with dynamic choices."""
        super().__init__(*args, **kwargs)

        # Ensure original_language choices are always up to date
        self.fields["original_language"].choices = [("", "Any language")] + list(
            settings.WAGTAIL_CONTENT_LANGUAGES
        )

        # Build exists_in_language choices dynamically
        exists_in_choices = [
            ("", "Any language"),
            (self.ALL_LANGUAGES, "All languages"),
        ]

        # Only add "Core languages" option if WAGTAIL_CORE_LANGUAGES is defined
        if (
            hasattr(settings, "WAGTAIL_CORE_LANGUAGES")
            and settings.WAGTAIL_CORE_LANGUAGES
        ):
            exists_in_choices.append((self.CORE_LANGUAGES, "Core languages"))

        exists_in_choices.extend(list(settings.WAGTAIL_CONTENT_LANGUAGES))

        self.fields["exists_in_language"].choices = exists_in_choices
