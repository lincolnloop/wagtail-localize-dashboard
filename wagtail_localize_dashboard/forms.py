"""Forms for filtering the translation dashboard."""

from typing import Any

from django import forms
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from wagtail.models import Locale

from .settings import get_setting


class ProgressFilterForm(forms.Form):
    """Filter form for the translation progress dashboard."""

    ALL_LANGUAGES = "__all__"
    CORE_LANGUAGES = "__core__"

    search = forms.CharField(
        required=False,
        label=_("Search"),
        widget=forms.TextInput(
            attrs={
                "class": "w-field__input",
                "placeholder": _("Search by title or slug..."),
            }
        ),
    )

    translation_key = forms.UUIDField(
        required=False,
        label=_("Translation Key"),
        widget=forms.TextInput(
            attrs={
                "class": "w-field__input",
                "placeholder": _("Filter by translation key..."),
            }
        ),
    )

    original_language = forms.ChoiceField(
        choices=[],  # Will be populated in __init__
        required=False,
        label=_("Original Language"),
        widget=forms.Select(attrs={"class": "w-field__input"}),
    )

    exists_in_language = forms.ChoiceField(
        choices=[],  # Will be populated in __init__
        required=False,
        label=_("Exists In"),
        widget=forms.Select(attrs={"class": "w-field__input"}),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with dynamic choices."""
        super().__init__(*args, **kwargs)

        # Build language choices from Locale objects that are in WAGTAIL_CONTENT_LANGUAGES
        language_map = dict(settings.WAGTAIL_CONTENT_LANGUAGES)
        configured_codes = list(language_map.keys())
        active_languages = [
            (locale.language_code, language_map[locale.language_code])
            for locale in Locale.objects.filter(
                language_code__in=configured_codes
            ).order_by("language_code")
        ]

        self.fields["original_language"].choices = [
            ("", _("Any language"))
        ] + active_languages

        # Build exists_in_language choices dynamically
        exists_in_choices = [
            ("", _("Any language")),
            (self.ALL_LANGUAGES, _("All languages")),
        ]

        # Only add "Core languages" option if WAGTAIL_CORE_LANGUAGES is defined
        if (
            hasattr(settings, "WAGTAIL_CORE_LANGUAGES")
            and settings.WAGTAIL_CORE_LANGUAGES
        ):
            exists_in_choices.append((self.CORE_LANGUAGES, _("Core languages")))

        exists_in_choices.extend(active_languages)

        self.fields["exists_in_language"].choices = exists_in_choices

        # Add column_filter field if options are configured
        column_filter_options = get_setting("COLUMN_FILTER_OPTIONS")
        if column_filter_options:
            column_filter_choices = [("", _("All languages"))]
            for option_id, option_label, _option_locales in column_filter_options:
                column_filter_choices.append((option_id, option_label))
            self.fields["column_filter"] = forms.ChoiceField(
                choices=column_filter_choices,
                required=False,
                label=_("Show languages"),
                widget=forms.Select(attrs={"class": "w-field__input"}),
            )


class SnippetProgressFilterForm(ProgressFilterForm):
    """
    Filter form for the snippet translation progress dashboard.

    Identical to ProgressFilterForm except there is no search field —
    snippets do not share a common searchable column the way pages share title/slug.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields.pop("search", None)
