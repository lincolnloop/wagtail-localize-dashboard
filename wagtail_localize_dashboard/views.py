"""Views for the translation progress dashboard."""

from typing import Any, Dict, List

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Min, Q, QuerySet
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic import ListView

from wagtail.admin.views.generic.base import BaseListingView
from wagtail.models import DraftStateMixin, Page

from .forms import ProgressFilterForm, SnippetProgressFilterForm
from .models import SnippetTranslationProgress, TranslationProgress
from .settings import get_setting, get_tracked_snippet_models
from .utils import get_original_objects


@method_decorator(staff_member_required, name="dispatch")
@method_decorator(never_cache, name="dispatch")
class ProgressDashboardView(ListView, BaseListingView):
    """
    Dashboard view showing translation progress for all pages.

    Features:
    - Lists all original pages (not translations)
    - Shows translation progress for each locale
    - Color-coded status indicators
    - Filtering by language, search, translation key
    - Pagination
    """

    model = Page
    template_name = "wagtail_localize_dashboard/dashboard.html"
    context_object_name = "pages"
    paginate_by = get_setting("ITEMS_PER_PAGE", 50)

    def get_filter_form(self):
        """Lazily create and cache the filter form instance."""
        if not hasattr(self, "_filter_form"):
            self._filter_form = ProgressFilterForm(self.request.GET)
        return self._filter_form

    def get_queryset(self) -> QuerySet[Page]:
        """
        Get original pages only, excluding root pages and translations.

        Returns:
            QuerySet of original Page objects with progress data prefetched
        """
        # Get all pages (live and draft), excluding root pages
        # Exclude root (depth=1) and locale roots (depth=2)
        all_pages = Page.objects.filter(depth__gt=2).select_related("locale")

        # Get original pages only (min ID per translation_key)
        min_ids_by_translation_key = (
            all_pages.order_by("translation_key")
            .values("translation_key")
            .annotate(min_id=Min("id"))
            .values_list("min_id", flat=True)
        )

        # Get the original pages
        pages_qs = Page.objects.filter(id__in=min_ids_by_translation_key).order_by(
            "title"
        )

        # Apply filters
        form = self.get_filter_form()
        if not form.is_valid():
            pages_qs = pages_qs.none()
        else:
            # Filter by translation key
            translation_key = form.cleaned_data.get("translation_key")
            if translation_key:
                pages_qs = pages_qs.filter(translation_key=translation_key)

            # Filter by search query
            search_query = form.cleaned_data.get("search")
            if search_query:
                pages_qs = pages_qs.filter(
                    Q(title__icontains=search_query) | Q(slug__icontains=search_query)
                )

            # Filter by original language
            if form.cleaned_data.get("original_language"):
                pages_qs = pages_qs.filter(
                    locale__language_code=form.cleaned_data["original_language"]
                )

            # Filter by whether page exists in a particular language
            exists_in_language = form.cleaned_data.get("exists_in_language")
            if exists_in_language:
                if exists_in_language == ProgressFilterForm.ALL_LANGUAGES:
                    # Special case: filter for pages that exist in ALL languages
                    num_languages = len(settings.WAGTAIL_CONTENT_LANGUAGES)

                    translation_keys_in_all = (
                        all_pages.order_by("translation_key")
                        .values("translation_key")
                        .annotate(locale_count=Count("locale", distinct=True))
                        .filter(locale_count=num_languages)
                        .values_list("translation_key", flat=True)
                    )
                    pages_qs = pages_qs.filter(
                        translation_key__in=translation_keys_in_all
                    )

                elif exists_in_language == ProgressFilterForm.CORE_LANGUAGES:
                    # Special case: filter for pages in ALL core languages
                    # Only process if WAGTAIL_CORE_LANGUAGES is defined
                    if (
                        hasattr(settings, "WAGTAIL_CORE_LANGUAGES")
                        and settings.WAGTAIL_CORE_LANGUAGES
                    ):
                        core_language_codes = [
                            lang_code
                            for lang_code, lang_name in settings.WAGTAIL_CORE_LANGUAGES
                        ]

                        # Get translation keys that exist in all core languages
                        translation_keys_sets = []
                        for core_lang in core_language_codes:
                            keys = set(
                                all_pages.filter(locale__language_code=core_lang)
                                .values_list("translation_key", flat=True)
                                .distinct()
                            )
                            translation_keys_sets.append(keys)

                        # Intersection of all sets
                        if translation_keys_sets:
                            translation_keys_in_all_core = set.intersection(
                                *translation_keys_sets
                            )
                            pages_qs = pages_qs.filter(
                                translation_key__in=translation_keys_in_all_core
                            )
                        else:
                            pages_qs = pages_qs.none()
                    else:
                        # CORE_LANGUAGES not defined, treat as no filter
                        pass
                else:
                    # Filter for pages that exist in specific language
                    translation_keys_with_locale = (
                        all_pages.filter(locale__language_code=exists_in_language)
                        .values_list("translation_key", flat=True)
                        .distinct()
                    )
                    pages_qs = pages_qs.filter(
                        translation_key__in=translation_keys_with_locale
                    )

        # Prefetch locale data for pages
        return pages_qs.select_related("locale")

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        """
        Add translation progress data to context.

        Returns:
            dict with pages_with_progress and filter_form
        """
        context = super().get_context_data(**kwargs)

        # Get all page ids in the current page of results
        page_ids = [page.id for page in context["pages"]]

        # Fetch ALL progress records for these pages with related pages prefetched
        # Using select_related to prefetch translated_page and its locale in a single query
        progress_by_page = {}
        if page_ids:
            progress_records = TranslationProgress.objects.filter(
                source_page_id__in=page_ids
            ).select_related("translated_page", "translated_page__locale")

            # Group by source page ID
            for progress in progress_records:
                if progress.source_page_id not in progress_by_page:
                    progress_by_page[progress.source_page_id] = []
                progress_by_page[progress.source_page_id].append(progress)

        # Build pages_with_progress using the prefetched data
        pages_with_progress = []
        for page in context["pages"]:
            progress_records = progress_by_page.get(page.id, [])

            # Get the proper edit URL using Wagtail's URL routing
            try:
                edit_url = reverse("wagtailadmin_pages:edit", args=[page.id])
            except Exception:
                edit_url = "#"

            pages_with_progress.append(
                {
                    "page": page,
                    "translations": [p.to_dict() for p in progress_records],
                    "edit_url": edit_url,
                    "view_url": page.get_url() if hasattr(page, "get_url") else "#",
                }
            )

        # Apply column filter: only affects which translation buttons are
        # visible, not which rows appear. Rows with no matching translations
        # will show "No translations" via existing template logic.
        filter_form = self.get_filter_form()
        column_filter_label = ""
        if filter_form.is_valid():
            selected_filter = filter_form.cleaned_data.get("column_filter", "")
            if selected_filter:
                column_filter_options = get_setting("COLUMN_FILTER_OPTIONS")
                match = next(
                    (
                        (label, locales)
                        for fid, label, locales in column_filter_options
                        if fid == selected_filter
                    ),
                    None,
                )
                if match:
                    column_filter_label = match[0]
                    filter_locales_set = set(match[1])
                    for page_data in pages_with_progress:
                        page_data["translations"] = [
                            t
                            for t in page_data["translations"]
                            if t["locale"] in filter_locales_set
                        ]

        context["pages_with_progress"] = pages_with_progress
        context["filter_form"] = filter_form
        context["column_filter_label"] = column_filter_label

        return context


@method_decorator(staff_member_required, name="dispatch")
@method_decorator(never_cache, name="dispatch")
class SnippetProgressDashboardView(ListView, BaseListingView):
    """
    Dashboard view showing translation progress for all tracked snippets.

    Returns a sorted Python list rather than a QuerySet because results
    span multiple models. Django's Paginator works with lists as well as
    QuerySets, so ListView handles pagination normally.
    """

    template_name = "wagtail_localize_dashboard/snippet_dashboard.html"
    context_object_name = "snippets"
    paginate_by = get_setting("ITEMS_PER_PAGE", 50)

    def get_filter_form(self) -> SnippetProgressFilterForm:
        if not hasattr(self, "_filter_form"):
            self._filter_form = SnippetProgressFilterForm(self.request.GET)
        return self._filter_form

    def get_queryset(self) -> List[Any]:
        """
        Build the combined, filtered, sorted list of original snippets across
        all tracked models.

        Filters are applied at the database level per model before combining,
        so only the matching rows are loaded into memory.
        """
        form = self.get_filter_form()
        tracked_models = get_tracked_snippet_models()

        if not form.is_valid():
            return []

        original_language = form.cleaned_data.get("original_language")
        translation_key = form.cleaned_data.get("translation_key")
        exists_in_language = form.cleaned_data.get("exists_in_language")
        num_languages = len(settings.WAGTAIL_CONTENT_LANGUAGES)

        combined: List[Any] = []
        for model in tracked_models:
            qs = get_original_objects(model).select_related("locale")

            if original_language:
                qs = qs.filter(locale__language_code=original_language)

            if translation_key:
                qs = qs.filter(translation_key=translation_key)

            if exists_in_language:
                if exists_in_language == SnippetProgressFilterForm.ALL_LANGUAGES:
                    translation_keys_in_all = (
                        model.objects.values("translation_key")
                        .annotate(locale_count=Count("locale", distinct=True))
                        .filter(locale_count=num_languages)
                        .values_list("translation_key", flat=True)
                    )
                    qs = qs.filter(translation_key__in=translation_keys_in_all)

                elif exists_in_language == SnippetProgressFilterForm.CORE_LANGUAGES:
                    if (
                        hasattr(settings, "WAGTAIL_CORE_LANGUAGES")
                        and settings.WAGTAIL_CORE_LANGUAGES
                    ):
                        core_codes = [
                            code for code, _ in settings.WAGTAIL_CORE_LANGUAGES
                        ]
                        key_sets = [
                            set(
                                model.objects.filter(locale__language_code=code)
                                .values_list("translation_key", flat=True)
                                .distinct()
                            )
                            for code in core_codes
                        ]
                        if key_sets:
                            qs = qs.filter(
                                translation_key__in=set.intersection(*key_sets)
                            )
                        else:
                            qs = qs.none()

                else:
                    translation_keys = (
                        model.objects.filter(locale__language_code=exists_in_language)
                        .values_list("translation_key", flat=True)
                        .distinct()
                    )
                    qs = qs.filter(translation_key__in=translation_keys)

            combined.extend(qs)

        combined.sort(key=lambda s: (type(s)._meta.verbose_name, str(s)))
        return combined

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)

        page_snippets: List[Any] = context["snippets"]

        # Group snippets on this page by content type so we can fetch all
        # their progress records in as few queries as possible.
        ct_to_pks: Dict[int, List[int]] = {}
        ct_cache: Dict[type, ContentType] = {}
        for snippet in page_snippets:
            model_class = type(snippet)
            if model_class not in ct_cache:
                ct_cache[model_class] = ContentType.objects.get_for_model(model_class)
            ct = ct_cache[model_class]
            ct_to_pks.setdefault(ct.pk, []).append(snippet.pk)

        # One DB query (plus one per content type for the GFK prefetch).
        progress_by_key: Dict[tuple, List[SnippetTranslationProgress]] = {}
        if ct_to_pks:
            q = Q()
            for ct_id, pks in ct_to_pks.items():
                q |= Q(content_type_id=ct_id, source_object_id__in=pks)

            records = (
                SnippetTranslationProgress.objects.filter(q)
                .select_related("translated_locale", "content_type")
                .prefetch_related("translated")
            )
            for record in records:
                key = (record.content_type_id, record.source_object_id)
                progress_by_key.setdefault(key, []).append(record)

        # Build the per-snippet dicts used by the template.
        snippets_with_progress = []
        for snippet in page_snippets:
            model_class = type(snippet)
            ct = ct_cache[model_class]
            key = (ct.pk, snippet.pk)
            progress_list = progress_by_key.get(key, [])

            try:
                edit_url = reverse(
                    f"wagtailsnippets_{ct.app_label}_{ct.model}:edit",
                    args=[snippet.pk],
                )
            except Exception:
                edit_url = "#"

            snippets_with_progress.append(
                {
                    "snippet": snippet,
                    "display_str": str(snippet),
                    "type_label": model_class._meta.verbose_name,
                    "has_draft_state": issubclass(model_class, DraftStateMixin),
                    "edit_url": edit_url,
                    "translations": [p.to_dict() for p in progress_list],
                }
            )

        # Column filter: limits which translation buttons are visible; rows
        # with no matching translations still appear (same behaviour as pages).
        filter_form = self.get_filter_form()
        column_filter_label = ""
        if filter_form.is_valid():
            selected_filter = filter_form.cleaned_data.get("column_filter", "")
            if selected_filter:
                column_filter_options = get_setting("COLUMN_FILTER_OPTIONS")
                match = next(
                    (
                        (label, locales)
                        for fid, label, locales in column_filter_options
                        if fid == selected_filter
                    ),
                    None,
                )
                if match:
                    column_filter_label = match[0]
                    filter_locales_set = set(match[1])
                    for snippet_data in snippets_with_progress:
                        snippet_data["translations"] = [
                            t
                            for t in snippet_data["translations"]
                            if t["locale"] in filter_locales_set
                        ]

        context["snippets_with_progress"] = snippets_with_progress
        context["filter_form"] = filter_form
        context["column_filter_label"] = column_filter_label

        return context
