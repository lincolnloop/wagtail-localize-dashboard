"""URL configuration for the translation progress dashboard."""

from django.urls import path

from .views import ProgressDashboardView, SnippetProgressDashboardView

app_name = "wagtail_localize_dashboard"

urlpatterns = [
    path("", ProgressDashboardView.as_view(), name="dashboard"),
    path("snippets/", SnippetProgressDashboardView.as_view(), name="snippet_dashboard"),
]
