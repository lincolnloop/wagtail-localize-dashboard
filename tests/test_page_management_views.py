from datetime import datetime, timezone

import pytest
from django.contrib.auth.models import Group, Permission
from django.contrib.messages import get_messages
from django.test import override_settings
from django.urls import reverse
from django.utils.http import urlencode
from pytest_django.asserts import assertInHTML, assertRedirects
from wagtail.models import GroupPagePermission, Page
from wagtail_localize.models import (
    StringSegment,
    StringTranslation,
    Translation,
    TranslationSource,
)

from tests.helpers import run_on_commit, target_of
from tests.models import SegmentedPage


def give_submit_translation_permission(user):
    user.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="wagtail_localize", codename="submit_translation"
        )
    )


def give_page_permissions(user, page, *permission_types):
    group = Group.objects.create(name=f"Test Page Editors {Group.objects.count()}")
    for permission_type in permission_types:
        GroupPagePermission.objects.create(
            group=group, page=page, permission_type=permission_type
        )
    user.groups.add(group)


def give_page_edit_permission(user, page):
    give_page_permissions(user, page, "change")


def translate_segments(source, locale, stop, start=0, **defaults):
    """Translate the source's segments [start:stop] into locale."""
    segments = StringSegment.objects.filter(source=source).order_by("order")
    for segment in segments[start:stop]:
        StringTranslation.objects.update_or_create(
            translation_of=segment.string,
            context=segment.context,
            locale=locale,
            defaults={
                "data": f"{locale.language_code} {segment.string.data}",
                **defaults,
            },
        )


def publish(translation):
    """Write the translations into a live target page."""
    with run_on_commit:
        translation.save_target(publish=True)


@pytest.fixture
def segmented_page(home_page, locale_en):
    """A page with exactly 10 segments: title, slug and 8 paragraphs."""
    page = SegmentedPage(
        title="Segmented Page",
        slug="segmented-page",
        locale=locale_en,
        body="".join(f"<p>Paragraph {i}</p>" for i in range(1, 9)),
    )
    home_page.add_child(instance=page)
    return page


@pytest.fixture
def segmented_source(segmented_page):
    source, _ = TranslationSource.get_or_create_from_instance(segmented_page)
    assert StringSegment.objects.filter(source=source).count() == 10
    return source


class TestPageManagementView:
    """Tests for the page translation management view."""

    @staticmethod
    def url(page):
        return reverse(
            "wagtail_localize_dashboard:manage_translations", args=(page.pk,)
        )

    def test_url(self, test_page):
        test_page.pk = 999
        assert self.url(test_page) == "/admin/translations/manage/pages/999/"

    def test_requires_authentication(self, client, test_page):
        url = self.url(test_page)

        response = client.get(url)

        assert response.status_code == 302
        wagtail_login = reverse("wagtailadmin_login")
        assert response.url == f"{wagtail_login}?next={url}"

    def test_accessible_by_admin(self, admin_client, test_page_with_translations):
        url = self.url(test_page_with_translations)

        response = admin_client.get(url)

        assert response.status_code == 200
        assert b"Manage Translations" in response.content

    def test_unknown_page_is_404(self, admin_client, test_page_with_translations):
        test_page_with_translations.pk = 999999999
        url = self.url(test_page_with_translations)

        response = admin_client.get(url)

        assert response.status_code == 404

    def test_page_without_translations_is_404(self, admin_client, test_page):
        url = self.url(test_page)

        response = admin_client.get(url)

        assert response.status_code == 404

    def test_translated_page_redirects_to_source(
        self, admin_client, test_page_with_translations, locale_de
    ):
        # The German page has no TranslationSource of its own, so the view falls
        # back to the dashboard's original: the lowest id for the translation key.
        de_page = target_of(test_page_with_translations, locale_de)

        response = admin_client.get(self.url(de_page))

        assertRedirects(response, self.url(test_page_with_translations))

    def test_alias_page_redirects_to_source(
        self, admin_client, test_page_with_translations, locale_fr
    ):
        fr_alias = test_page_with_translations.copy_for_translation(
            locale_fr, copy_parents=True, alias=True
        )

        response = admin_client.get(self.url(fr_alias))

        assertRedirects(response, self.url(test_page_with_translations))

    def test_translated_page_shows_source_translations(
        self, admin_client, test_page_with_translations, locale_de
    ):
        de_page = target_of(test_page_with_translations, locale_de)
        source = TranslationSource.objects.get_for_instance(test_page_with_translations)

        response = admin_client.get(self.url(de_page), follow=True)

        content = response.content.decode()
        assertInHTML(
            '<h1 class="w-sr-only">Manage Translations: Test Page</h1>', content
        )
        translations = Translation.objects.filter(source=source)
        assert translations.count() == 2
        for translation in translations:
            assert f'data-object-id="{translation.pk}"' in content

    def test_requires_submit_translation_permission(
        self, test_page_with_translations, wagtail_client, wagtail_user
    ):
        give_page_edit_permission(wagtail_user, test_page_with_translations)
        url = self.url(test_page_with_translations)

        response = wagtail_client.get(url)

        assert response.status_code == 403

    def test_requires_page_editing_permission(
        self, test_page_with_translations, wagtail_client, wagtail_user
    ):
        give_submit_translation_permission(wagtail_user)
        url = self.url(test_page_with_translations)

        response = wagtail_client.get(url)

        assert response.status_code == 403

    def test_accessible_to_wagtail_users(
        self, test_page_with_translations, wagtail_client, wagtail_user
    ):
        give_submit_translation_permission(wagtail_user)
        give_page_edit_permission(wagtail_user, test_page_with_translations)
        url = self.url(test_page_with_translations)

        response = wagtail_client.get(url)

        assert response.status_code == 200
        assert b"Manage Translations" in response.content

    @pytest.fixture
    def get_content(self, admin_client, test_page_with_translations):

        def _get_content(page=test_page_with_translations):
            url = self.url(page)

            response = admin_client.get(url)

            return response.content.decode()

        return _get_content

    def test_heading(self, get_content):
        content = get_content()

        assertInHTML(
            '<h1 class="w-sr-only">Manage Translations: Test Page</h1>', content
        )

    def test_heading_escapes_page_title(self, get_content, test_page_with_translations):
        test_page_with_translations.title = "<b>Bold</b> Page"
        test_page_with_translations.save()

        content = get_content()

        assert "<b>Bold</b>" not in content
        assert "&lt;b&gt;Bold&lt;/b&gt; Page" in content

    def test_edit_page_header_button(self, get_content, test_page_with_translations):
        edit_page_url = reverse(
            "wagtailadmin_pages:edit", args=(test_page_with_translations.pk,)
        )
        edit_page_label = "Edit English Page"

        content = get_content()

        assert f'href="{edit_page_url}"' in content
        assert edit_page_label in content

    def test_translate_more_header_button(
        self, get_content, test_page_with_translations, locale_fr
    ):
        translate_more_url = reverse(
            "wagtail_localize:submit_page_translation",
            args=(test_page_with_translations.pk,),
        )
        translate_more_label = "Translate into more locales"

        content = get_content()

        assert translate_more_url in content
        assert translate_more_label in content

    def test_translate_more_header_button_shown_for_alias_locales(
        self, get_content, test_page_with_translations, locale_de
    ):
        translate_more_url = reverse(
            "wagtail_localize:submit_page_translation",
            args=(test_page_with_translations.pk,),
        )
        translate_more_label = "Translate into more locales"
        Page.objects.filter(
            pk=target_of(test_page_with_translations, locale_de).pk
        ).update(alias_of=test_page_with_translations)
        Translation.objects.filter(target_locale=locale_de).delete()

        content = get_content()

        assert translate_more_url in content
        assert translate_more_label in content

    def test_translate_more_header_button_requires_an_untranslated_locale(
        self, get_content, test_page_with_translations
    ):
        translate_more_url = reverse(
            "wagtail_localize:submit_page_translation",
            args=(test_page_with_translations.pk,),
        )
        translate_more_label = "Translate into more locales"

        content = get_content()

        assert translate_more_url not in content
        assert translate_more_label not in content

    def test_sync_translations_header_button(
        self, get_content, test_page_with_translations
    ):
        source = TranslationSource.objects.get_for_instance(test_page_with_translations)
        sync_translations_url = reverse(
            "wagtail_localize:update_translations", args=(source.pk,)
        )
        sync_translations_label = "Sync translated pages"
        test_page_with_translations.title = "Changed Test Page"
        test_page_with_translations.save_revision().publish()

        content = get_content()

        assert sync_translations_url in content
        assert sync_translations_label in content

    def test_sync_translations_header_button_requires_an_unsynced_source_change(
        self, get_content, test_page_with_translations
    ):
        source = TranslationSource.objects.get_for_instance(test_page_with_translations)
        sync_translations_url = reverse(
            "wagtail_localize:update_translations", args=(source.pk,)
        )
        sync_translations_label = "Sync translated pages"

        content = get_content()

        assert sync_translations_url not in content
        assert sync_translations_label not in content

    def test_sync_translations_header_button_requires_an_enabled_translation(
        self, get_content, test_page_with_translations
    ):
        source = TranslationSource.objects.get_for_instance(test_page_with_translations)
        sync_translations_url = reverse(
            "wagtail_localize:update_translations", args=(source.pk,)
        )
        sync_translations_label = "Sync translated pages"
        test_page_with_translations.title = "Changed Test Page"
        test_page_with_translations.save_revision().publish()
        Translation.objects.filter(source=source).update(enabled=False)

        content = get_content()

        assert sync_translations_url not in content
        assert sync_translations_label not in content

    def test_shows_bulk_action_controls(self, get_content):
        content = get_content()

        assert "data-bulk-action-select-all-checkbox" in content
        assert 'data-bulk-action-footer="TRANSLATION"' in content
        for action in ("publish", "unpublish"):
            url = reverse(
                "wagtail_bulk_action", args=("wagtail_localize", "translation", action)
            )
            assert f'href="{url}"' in content

    def test_does_not_show_source_locale(
        self, get_content, test_page_with_translations, locale_de, locale_en
    ):
        # Translating the German page back into English targets the source locale.
        de_source, _ = TranslationSource.get_or_create_from_instance(
            target_of(test_page_with_translations, locale_de)
        )
        back_translation = Translation.objects.create(
            source=de_source, target_locale=locale_en
        )
        source = TranslationSource.objects.get_for_instance(test_page_with_translations)

        content = get_content()

        assert f'data-object-id="{back_translation.pk}"' not in content
        for translation in Translation.objects.filter(source=source):
            assert f'data-object-id="{translation.pk}"' in content

    @override_settings(WAGTAILLOCALIZE_DISABLE_ON_DELETE=True)
    def test_shows_disabled_translations(
        self, get_content, test_page_with_translations, locale_de, locale_fr
    ):
        source = TranslationSource.objects.get_for_instance(test_page_with_translations)
        # Disabled by wagtail-localize when its page was deleted.
        target_of(test_page_with_translations, locale_de).delete()
        de_translation = Translation.objects.get(source=source, target_locale=locale_de)
        assert de_translation.enabled is False
        # Disabled, and its page was never created.
        fr_translation = Translation.objects.create(
            source=source, target_locale=locale_fr, enabled=False
        )

        content = get_content()

        for translation, name in (
            (de_translation, "German"),
            (fr_translation, "French"),
        ):
            assert f'data-object-id="{translation.pk}"' in content
            assert name in content
        assert content.count("Not created yet") == 2

    def test_shows_translation_checkboxes(
        self, get_content, test_page_with_translations, locale_fr
    ):
        source = TranslationSource.objects.get_for_instance(test_page_with_translations)
        Translation.objects.create(source=source, target_locale=locale_fr)  # no page

        content = get_content()

        translations = Translation.objects.filter(source=source)
        assert translations.count() == 3
        for translation in translations:
            assert f'data-object-id="{translation.pk}"' in content

    def test_shows_translation_names(
        self, get_content, test_page_with_translations, locale_es
    ):
        Translation.objects.filter(target_locale=locale_es).update(enabled=False)

        content = get_content()

        assert "German" in content
        assert "Spanish" in content

    def test_shows_translation_page_links(
        self, get_content, test_page_with_translations, locale_de, locale_es
    ):
        content = get_content()

        for locale in (locale_de, locale_es):
            translated_page = target_of(test_page_with_translations, locale)
            edit_url = reverse("wagtailadmin_pages:edit", args=(translated_page.pk,))
            assert f'href="{edit_url}"' in content

    def test_shows_translated_percentage(
        self,
        get_content,
        segmented_page,
        segmented_source,
        locale_de,
        locale_es,
        locale_fr,
        locale_it,
    ):
        for locale, translated in (
            (locale_de, 10),
            (locale_es, 8),
            (locale_fr, 5),
            (locale_it, 0),
        ):
            Translation.objects.create(source=segmented_source, target_locale=locale)
            translate_segments(segmented_source, locale, translated)

        content = get_content(segmented_page)

        assertInHTML(
            '<span class="text-success">100% (10 of 10)</span>', content, count=1
        )
        assertInHTML(
            '<span class="text-warning">80% (8 of 10)</span>', content, count=1
        )
        assertInHTML('<span class="text-danger">50% (5 of 10)</span>', content, count=1)
        assertInHTML('<span class="text-danger">0% (0 of 10)</span>', content, count=1)

    def test_shows_published_percentage(
        self,
        get_content,
        segmented_page,
        segmented_source,
        locale_de,
        locale_es,
        locale_fr,
        locale_it,
    ):
        # Every locale ends up 100% translated; only the first `published` are live.
        for locale, published in ((locale_de, 10), (locale_es, 8), (locale_fr, 5)):
            translation = Translation.objects.create(
                source=segmented_source, target_locale=locale
            )
            translate_segments(segmented_source, locale, published)
            publish(translation)
            translate_segments(segmented_source, locale, 10, start=published)
        # No target page, so nothing can be published.
        Translation.objects.create(source=segmented_source, target_locale=locale_it)
        translate_segments(segmented_source, locale_it, 10)

        content = get_content(segmented_page)

        # Four 100% translated, plus 100% published for German.
        assertInHTML(
            '<span class="text-success">100% (10 of 10)</span>', content, count=5
        )
        assertInHTML(
            '<span class="text-warning">80% (8 of 10)</span>', content, count=1
        )
        assertInHTML('<span class="text-danger">50% (5 of 10)</span>', content, count=1)
        assertInHTML("<span>-</span>", content, count=1)

    def test_shows_page_status(
        self, get_content, test_page_with_translations, locale_de, locale_es, locale_fr
    ):
        Page.objects.filter(
            pk=target_of(test_page_with_translations, locale_de).pk
        ).update(live=False)
        Page.objects.filter(
            pk=target_of(test_page_with_translations, locale_es).pk
        ).update(
            live=True,
            has_unpublished_changes=False,
            last_published_at=datetime(2026, 1, 1, 15, 9, tzinfo=timezone.utc),
        )
        source = TranslationSource.objects.get_for_instance(test_page_with_translations)
        Translation.objects.create(source=source, target_locale=locale_fr)  # no page

        content = get_content()

        assertInHTML(
            '<td><span class="w-status" role="status">draft</span></td', content
        )
        assertInHTML(
            '<td><span class="w-status w-status--primary" role="status">live</span><br>Last published Jan 1, 2026</td>',
            content,
        )
        assertInHTML("<td>Not created yet</td>", content)

    def test_shows_translated_via(
        self,
        get_content,
        admin_user,
        segmented_page,
        segmented_source,
        locale_de,
        locale_es,
        locale_fr,
    ):
        de_translation = Translation.objects.create(
            source=segmented_source, target_locale=locale_de
        )
        translate_segments(
            segmented_source,
            locale_de,
            1,
            tool_name="PO file",
            last_translated_by=admin_user,
        )
        translate_segments(
            segmented_source,
            locale_de,
            3,
            start=1,
            tool_name="",
            last_translated_by=admin_user,
        )
        publish(de_translation)
        es_translation = Translation.objects.create(
            source=segmented_source, target_locale=locale_es
        )
        translate_segments(
            segmented_source, locale_es, 2, tool_name="", last_translated_by=None
        )
        publish(es_translation)
        Translation.objects.create(
            source=segmented_source, target_locale=locale_fr
        )  # no page

        content = get_content(segmented_page)

        assertInHTML("<ul><li>Manual (2)</li><li>PO file (1)</li></ul>", content)
        assertInHTML("<ul><li>Other tool (2)</li></ul>", content)
        assert "Not translated yet" in content


def bulk_action_url(action, translations, next_url=None):
    params = [("id", translation.pk) for translation in translations]
    if next_url:
        params.append(("next", next_url))
    url = reverse(
        "wagtail_bulk_action", args=("wagtail_localize", "translation", action)
    )
    return f"{url}?{urlencode(params)}"


def context_items(response, key="items"):
    """The Translations listed under ``key`` on the confirmation page."""
    return [
        item["item"] if isinstance(item, dict) else item
        for item in response.context[key]
    ]


@pytest.fixture
def translations(test_page_with_translations, locale_de, locale_es, locale_fr):
    """German and Spanish translations with live pages; French with no page."""
    source = TranslationSource.objects.get_for_instance(test_page_with_translations)
    Translation.objects.create(source=source, target_locale=locale_fr)
    # save_target() would defer publishing to on_commit, which the fixture never runs.
    Page.objects.filter(
        translation_key=test_page_with_translations.translation_key,
        locale__in=(locale_de, locale_es),
    ).update(live=True)
    return {
        translation.target_locale.language_code: translation
        for translation in Translation.objects.filter(source=source)
    }


@pytest.fixture
def root_editor(wagtail_user, root_page):
    """A user who can edit every page, but not publish or unpublish any."""
    give_page_permissions(wagtail_user, root_page, "change")
    return wagtail_user


class TestPublishAction:
    """Tests for the translation Publish action view."""

    def test_requires_authentication(self, client, translations):
        url = bulk_action_url("publish", [translations["de"]])

        response = client.get(url)

        assert response.status_code == 302
        assert response.url.startswith(reverse("wagtailadmin_login"))

    def test_get_shows_confirmation_without_publishing(
        self, admin_client, test_page_with_translations, translations, locale_de
    ):
        de_page = target_of(test_page_with_translations, locale_de)
        Page.objects.filter(pk=de_page.pk).update(live=False)

        response = admin_client.get(
            bulk_action_url("publish", [translations["de"], translations["fr"]])
        )

        assert response.status_code == 200
        assert set(context_items(response)) == {translations["de"], translations["fr"]}
        de_page.refresh_from_db()
        assert de_page.live is False
        assert not Page.objects.filter(
            translation_key=test_page_with_translations.translation_key,
            locale__language_code="fr",
        ).exists()

    def test_post_publishes_translations_into_target_pages(
        self,
        admin_client,
        django_capture_on_commit_callbacks,
        test_page_with_translations,
        translations,
        locale_de,
    ):
        de_page = target_of(test_page_with_translations, locale_de)
        Page.objects.filter(pk=de_page.pk).update(live=False)
        source = translations["de"].source
        translate_segments(source, locale_de, 1)  # the title

        with django_capture_on_commit_callbacks(execute=True):
            response = admin_client.post(
                bulk_action_url("publish", [translations["de"]])
            )

        assert response.status_code == 302
        de_page.refresh_from_db()
        assert de_page.live is True
        assert de_page.title == "de Test Page"

    def test_post_creates_and_publishes_missing_target_page(
        self,
        admin_client,
        django_capture_on_commit_callbacks,
        test_page_with_translations,
        translations,
        locale_fr,
    ):
        with django_capture_on_commit_callbacks(execute=True):
            response = admin_client.post(
                bulk_action_url("publish", [translations["fr"]])
            )

        assert response.status_code == 302
        fr_page = target_of(test_page_with_translations, locale_fr)
        assert fr_page.live is True

    def test_post_redirects_to_next_with_success_message(
        self, admin_client, django_capture_on_commit_callbacks, translations
    ):
        next_url = reverse("wagtail_localize_dashboard:manage_translations", args=(1,))

        with django_capture_on_commit_callbacks(execute=True):
            response = admin_client.post(
                bulk_action_url(
                    "publish", [translations["de"], translations["es"]], next_url
                )
            )

        assert response.status_code == 302
        assert response.url == next_url
        assert [str(m) for m in get_messages(response.wsgi_request)] == [
            "2 translations have been published"
        ]

    def test_disabled_translation_is_listed_as_ineligible(
        self, admin_client, translations
    ):
        translations["es"].enabled = False
        translations["es"].save()

        response = admin_client.get(
            bulk_action_url("publish", [translations["de"], translations["es"]])
        )

        assert context_items(response) == [translations["de"]]
        assert context_items(response, "items_ineligible") == [translations["es"]]

    def test_disabled_translation_is_not_published(
        self,
        admin_client,
        django_capture_on_commit_callbacks,
        test_page_with_translations,
        translations,
        locale_es,
    ):
        translations["es"].enabled = False
        translations["es"].save()
        translate_segments(translations["es"].source, locale_es, 1)  # the title

        with django_capture_on_commit_callbacks(execute=True):
            response = admin_client.post(
                bulk_action_url("publish", [translations["de"], translations["es"]])
            )
            assert response.status_code == 302

        assert target_of(test_page_with_translations, locale_es).title == "Test Page"
        assert [str(m) for m in get_messages(response.wsgi_request)] == [
            "1 translation has been published"
        ]

    def test_requires_publish_permission_on_target_page(
        self, wagtail_client, root_editor, translations
    ):
        response = wagtail_client.get(bulk_action_url("publish", [translations["de"]]))

        assert context_items(response) == []
        assert context_items(response, "items_with_no_access") == [translations["de"]]

    def test_publish_permission_on_target_page_is_sufficient(
        self, wagtail_client, root_editor, translations, test_page_with_translations
    ):
        de_page = target_of(
            test_page_with_translations, translations["de"].target_locale
        )
        give_page_permissions(root_editor, de_page, "publish")

        response = wagtail_client.get(bulk_action_url("publish", [translations["de"]]))

        assert context_items(response) == [translations["de"]]

    def test_missing_target_page_requires_publish_permission_on_source_page(
        self, wagtail_client, root_editor, translations
    ):
        response = wagtail_client.get(bulk_action_url("publish", [translations["fr"]]))

        assert context_items(response, "items_with_no_access") == [translations["fr"]]

    def test_missing_target_page_publish_permission_on_source_page_is_sufficient(
        self, wagtail_client, root_editor, translations, test_page_with_translations
    ):
        give_page_permissions(root_editor, test_page_with_translations, "publish")

        response = wagtail_client.get(bulk_action_url("publish", [translations["fr"]]))

        assert context_items(response) == [translations["fr"]]

    def test_post_skips_translations_without_permission(
        self,
        wagtail_client,
        django_capture_on_commit_callbacks,
        root_editor,
        test_page_with_translations,
        translations,
        locale_de,
    ):
        de_page = target_of(test_page_with_translations, locale_de)
        Page.objects.filter(pk=de_page.pk).update(live=False)

        with django_capture_on_commit_callbacks(execute=True):
            response = wagtail_client.post(
                bulk_action_url("publish", [translations["de"]])
            )

        assert response.status_code == 302
        de_page.refresh_from_db()
        assert de_page.live is False


class TestUnpublishAction:
    """Tests for the translation Unpublish action view."""

    def test_requires_authentication(self, client, translations):
        url = bulk_action_url("unpublish", [translations["de"]])

        response = client.get(url)

        assert response.status_code == 302
        assert response.url.startswith(reverse("wagtailadmin_login"))

    def test_get_shows_confirmation_without_unpublishing(
        self, admin_client, test_page_with_translations, translations, locale_de
    ):
        response = admin_client.get(bulk_action_url("unpublish", [translations["de"]]))

        assert response.status_code == 200
        assert context_items(response) == [translations["de"]]
        assert target_of(test_page_with_translations, locale_de).live is True

    def test_post_unpublishes_target_pages(
        self,
        admin_client,
        test_page_with_translations,
        translations,
        locale_de,
        locale_es,
    ):
        response = admin_client.post(
            bulk_action_url("unpublish", [translations["de"], translations["es"]])
        )

        assert response.status_code == 302

        assert target_of(test_page_with_translations, locale_de).live is False
        assert target_of(test_page_with_translations, locale_es).live is False

    def test_post_does_not_unpublish_source_page(
        self, admin_client, test_page_with_translations, translations
    ):
        response = admin_client.post(bulk_action_url("unpublish", [translations["de"]]))

        assert response.status_code == 302

        test_page_with_translations.refresh_from_db()
        assert test_page_with_translations.live is True

    def test_post_keeps_translation_syncing(self, admin_client, translations):
        response = admin_client.post(bulk_action_url("unpublish", [translations["de"]]))

        assert response.status_code == 302

        translations["de"].refresh_from_db()
        assert translations["de"].enabled is True

    def test_post_redirects_to_next_with_success_message(
        self, admin_client, translations
    ):
        next_url = reverse("wagtail_localize_dashboard:manage_translations", args=(1,))

        response = admin_client.post(
            bulk_action_url(
                "unpublish", [translations["de"], translations["es"]], next_url
            )
        )

        assert response.status_code == 302
        assert response.url == next_url
        assert [str(m) for m in get_messages(response.wsgi_request)] == [
            "2 translations have been unpublished"
        ]

    def test_disabled_translation_can_be_unpublished(
        self, admin_client, test_page_with_translations, translations, locale_de
    ):
        translations["de"].enabled = False
        translations["de"].save()

        response = admin_client.post(bulk_action_url("unpublish", [translations["de"]]))

        assert response.status_code == 302

        assert target_of(test_page_with_translations, locale_de).live is False

    def test_missing_and_draft_target_pages_are_listed_as_ineligible(
        self, admin_client, test_page_with_translations, translations, locale_es
    ):
        Page.objects.filter(
            pk=target_of(test_page_with_translations, locale_es).pk
        ).update(live=False)

        response = admin_client.get(
            bulk_action_url(
                "unpublish",
                [translations["de"], translations["es"], translations["fr"]],
            )
        )

        assert context_items(response) == [translations["de"]]
        assert set(context_items(response, "items_ineligible")) == {
            translations["es"],
            translations["fr"],
        }

    def test_post_skips_ineligible_translations(self, admin_client, translations):
        response = admin_client.post(
            bulk_action_url("unpublish", [translations["de"], translations["fr"]])
        )

        assert response.status_code == 302

        assert [str(m) for m in get_messages(response.wsgi_request)] == [
            "1 translation has been unpublished"
        ]

    def test_requires_unpublish_permission_on_target_page(
        self, wagtail_client, root_editor, translations
    ):
        response = wagtail_client.get(
            bulk_action_url("unpublish", [translations["de"]])
        )

        assert context_items(response) == []
        assert context_items(response, "items_with_no_access") == [translations["de"]]

    def test_unpublish_permission_on_target_page_is_sufficient(
        self, wagtail_client, root_editor, translations, test_page_with_translations
    ):
        de_page = target_of(
            test_page_with_translations, translations["de"].target_locale
        )
        give_page_permissions(root_editor, de_page, "publish")

        response = wagtail_client.get(
            bulk_action_url("unpublish", [translations["de"]])
        )

        assert context_items(response) == [translations["de"]]

    def test_post_skips_translations_without_permission(
        self, wagtail_client, root_editor, test_page_with_translations, translations
    ):
        response = wagtail_client.post(
            bulk_action_url("unpublish", [translations["de"]])
        )
        assert response.status_code == 302

        de_page = target_of(
            test_page_with_translations, translations["de"].target_locale
        )
        assert de_page.live is True
