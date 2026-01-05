"""
URL configuration for tests.
"""

from django.contrib import admin
from django.urls import include, path

from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls

urlpatterns = [
    path("django-admin/", admin.site.urls),
    # Dashboard URLs must come before wagtailadmin_urls to avoid being caught by admin catch-all
    path("admin/translations/", include("wagtail_localize_dashboard.urls")),
    path("admin/", include(wagtailadmin_urls)),
    path("", include(wagtail_urls)),
]
