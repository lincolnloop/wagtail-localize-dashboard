"""Views for the translation progress dashboard."""

from typing import Any, Dict

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Min, Q, QuerySet
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic import ListView

from wagtail.admin.views.generic.base import BaseListingView
from wagtail.models import Page

from .forms import ProgressFilterForm
from .models import TranslationProgress
from .settings import get_setting


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
        form = ProgressFilterForm(self.request.GET)
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

        context["pages_with_progress"] = pages_with_progress
        context["filter_form"] = ProgressFilterForm(self.request.GET)

        return context
