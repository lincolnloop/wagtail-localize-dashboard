"""Shared helpers for tests that publish and re-save translations."""

from contextlib import contextmanager
from unittest.mock import patch

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from wagtail.models import Locale, Page, Site
from wagtail_localize.models import (
    StringSegment,
    StringTranslation,
    Translation,
    TranslationSource,
)

# Ensure save_target() actually publishes, since wagtail-localize defers
# publishing to transaction.on_commit().
run_on_commit = patch.object(transaction, "on_commit", side_effect=lambda func: func())


def translate_all_segments_and_publish(source_object, locale):
    """Translate every segment of source_object into locale and push it live."""
    source, __ = TranslationSource.get_or_create_from_instance(source_object)
    translation, __ = Translation.objects.get_or_create(
        source=source, target_locale=locale
    )
    for segment in StringSegment.objects.filter(source=source).order_by("order"):
        StringTranslation.objects.update_or_create(
            translation_of=segment.string,
            context=segment.context,
            locale=locale,
            defaults={"data": f"DE {segment.context.path}"},
        )
    translation.save_target(publish=True)
    return source, translation


def get_first_segment_translation(source, locale):
    """Return the StringTranslation for the first segment of source."""
    segment = StringSegment.objects.filter(source=source).order_by("order").first()
    return StringTranslation.objects.get(
        translation_of=segment.string, context=segment.context, locale=locale
    )


def resave_first_segment_like_editor(
    source, locale, data=None, has_error=False, user=None
):
    """Repeat the write wagtail-localize's segment editor does."""
    stored = get_first_segment_translation(source, locale)
    StringTranslation.objects.update_or_create(
        translation_of_id=stored.translation_of_id,
        locale_id=locale.pk,
        context_id=stored.context_id,
        defaults={
            "data": stored.data if data is None else data,
            "translation_type": StringTranslation.TRANSLATION_TYPE_MANUAL,
            "tool_name": "",
            "last_translated_by": user,
            "has_error": has_error,
            "field_error": "",
        },
    )


def target_of(source_object, locale):
    """The translated instance of source_object in locale."""
    return type(source_object).objects.get(
        translation_key=source_object.translation_key, locale=locale
    )


def default_locale():
    """The locale Page.save() falls back to, created if it is missing."""
    locale, __ = Locale.objects.get_or_create(
        language_code=settings.LANGUAGE_CODE.split("-")[0]
    )
    return locale


def ensure_root_page():
    """Return the Wagtail root page, rebuilding it if a flush removed it."""
    # First, make sure the default Locale exists.
    default_locale()
    root = Page.objects.filter(depth=1).first()
    if root is None:
        root = Page(
            title="Root",
            slug="root",
            content_type=ContentType.objects.get_for_model(Page),
            path="0001",
            depth=1,
            numchild=0,
            url_path="/",
        )
        root.save()
    return root


def ensure_home_page():
    """Make sure the home page and the Site exist, and return the home page."""
    root = ensure_root_page()
    locale = default_locale()
    home = Page.objects.filter(slug="home", depth=2, locale=locale).first()
    if home is None:
        home = Page(
            title="Home",
            slug="home",
            content_type=ContentType.objects.get_for_model(Page),
            locale=locale,
        )
        root.add_child(instance=home)

    # Also, make sure the Site exists.
    if not Site.objects.filter(is_default_site=True).exists():
        Site.objects.create(
            hostname="localhost",
            port=80,
            site_name="Test Site",
            root_page=home,
            is_default_site=True,
        )
    return home


def create_or_replace_page(parent, slug):
    """A fresh child of parent, replacing any page an earlier test left behind."""
    Page.objects.filter(slug=slug).delete()
    page = Page(
        title=slug.replace("-", " ").title(),
        slug=slug,
        locale=default_locale(),
        content_type=ContentType.objects.get_for_model(Page),
    )
    parent.add_child(instance=page)
    return page


@contextmanager
def count_translation_progress_calls():
    """Count the calls to create_page_translation_progress()."""
    import wagtail_localize_dashboard.signals as sig
    import wagtail_localize_dashboard.utils as utils

    calls = {"n": 0, "kwargs": []}
    real = utils.create_page_translation_progress

    def counting(page, **kwargs):
        calls["n"] += 1
        calls["kwargs"].append(kwargs)
        return real(page, **kwargs)

    with (
        patch.object(utils, "create_page_translation_progress", counting),
        patch.object(sig, "create_page_translation_progress", counting),
    ):
        yield calls
