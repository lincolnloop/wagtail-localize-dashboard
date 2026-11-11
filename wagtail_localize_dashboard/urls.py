"""URL configuration for the translation progress dashboard."""

from django.urls import path

from .views import (
    PageTranslationsManageView,
    ProgressDashboardView,
    SnippetProgressDashboardView,
)

app_name = "wagtail_localize_dashboard"

urlpatterns = [
    path("", ProgressDashboardView.as_view(), name="dashboard"),
    path("snippets/", SnippetProgressDashboardView.as_view(), name="snippet_dashboard"),
    path(
        "manage/pages/<int:pk>/",
        PageTranslationsManageView.as_view(),
        name="manage_translations",
    ),
]
