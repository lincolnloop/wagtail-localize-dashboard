from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.http import urlencode
from pytest_django.asserts import assertInHTML
from wagtail.models import Page
from wagtail_localize.models import Translation, TranslationSource

from tests.helpers import (
    assert_stopped,
    assert_syncing,
    give_page_permissions,
    give_submit_translation_permission,
    table_row,
    target_of,
    translate_segments,
)


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

    def test_validation_error_skips_only_that_translation_with_error_message(
        self,
        admin_client,
        django_capture_on_commit_callbacks,
        test_page_with_translations,
        translations,
        locale_de,
        locale_es,
    ):
        de_page = target_of(test_page_with_translations, locale_de)
        es_page = target_of(test_page_with_translations, locale_es)
        Page.objects.filter(pk__in=(de_page.pk, es_page.pk)).update(live=False)
        translate_segments(translations["de"].source, locale_de, 1)  # the title
        real_save_target = Translation.save_target

        def save_target_failing_for_german(translation, **kwargs):
            real_save_target(translation, **kwargs)
            if translation.target_locale == locale_de:
                raise ValidationError({"title": "Invalid"})

        with (
            patch.object(
                Translation,
                "save_target",
                autospec=True,
                side_effect=save_target_failing_for_german,
            ),
            django_capture_on_commit_callbacks(execute=True),
        ):
            response = admin_client.post(
                bulk_action_url("publish", [translations["de"], translations["es"]])
            )

        assert response.status_code == 302
        assert [str(m) for m in get_messages(response.wsgi_request)] == [
            "1 translation has been published",
            "'Test Page' could not be published in German because of validation "
            "errors.",
        ]
        de_page.refresh_from_db()
        es_page.refresh_from_db()
        assert (de_page.live, de_page.title) == (False, "Test Page")
        assert es_page.live is True

    def test_alias_target_page_is_marked_as_converted(
        self, admin_client, test_page_with_translations, translations, locale_de
    ):
        Page.objects.filter(
            pk=target_of(test_page_with_translations, locale_de).pk
        ).update(alias_of=test_page_with_translations)

        response = admin_client.get(
            bulk_action_url("publish", [translations["de"], translations["es"]])
        )

        content = response.content.decode()
        assertInHTML(
            "<li>German (alias, will be converted to a regular page)</li>", content
        )
        assertInHTML("<li>Spanish</li>", content)

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

    def test_missing_target_page_requires_submit_translation_permission(
        self, wagtail_client, root_editor, translations, test_page_with_translations
    ):
        give_page_permissions(root_editor, test_page_with_translations, "publish")

        response = wagtail_client.get(bulk_action_url("publish", [translations["fr"]]))

        assert context_items(response, "items_with_no_access") == [translations["fr"]]

    def test_missing_target_page_submit_translation_permission_is_sufficient(
        self, wagtail_client, root_editor, translations
    ):
        give_submit_translation_permission(root_editor)

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


STOP = SimpleNamespace(
    type="stop_syncing",
    start_enabled=True,
    end_enabled=False,
    ineligible_heading="These translations are not syncing:",
    confirmation_texts={
        1: "Stop syncing the selected locale? It becomes an independent page that "
        "source changes no longer reach.",
        2: "Stop syncing the selected locales? They become independent pages that "
        "source changes no longer reach.",
    },
    success_messages={
        1: "1 translation has stopped syncing",
        2: "2 translations have stopped syncing",
    },
    assert_listed_state=assert_stopped,
)
RESTART = SimpleNamespace(
    type="restart_syncing",
    start_enabled=False,
    end_enabled=True,
    ineligible_heading="These translations are already syncing:",
    confirmation_texts={
        1: "Restart syncing this locale? It will open in the translation editor "
        "again, and edits made to it while it was not syncing may be replaced the "
        "next time it is published.",
        2: "Restart syncing these locales? They will open in the translation editor "
        "again, and edits made to them while they were not syncing may be replaced "
        "the next time they are published.",
    },
    success_messages={
        1: "1 translation has restarted syncing",
        2: "2 translations have restarted syncing",
    },
    assert_listed_state=assert_syncing,
)


def grant_submit_translation(user, root_page):
    give_submit_translation_permission(user)


def grant_root_edit(user, root_page):
    give_page_permissions(user, root_page, "change")


class TestSyncingActions:
    """Tests for the translation Stop syncing and Restart syncing action views."""

    @pytest.fixture(params=[STOP, RESTART], ids=["stop", "restart"])
    def action(self, request, translations):
        """The action, with every translation in the state it acts on."""
        Translation.objects.filter(
            pk__in=[translation.pk for translation in translations.values()]
        ).update(enabled=request.param.start_enabled)
        for translation in translations.values():
            translation.refresh_from_db()
        return request.param

    def test_requires_authentication(self, action, client, translations):
        response = client.get(bulk_action_url(action.type, [translations["de"]]))

        assert response.status_code == 302
        assert response.url.startswith(reverse("wagtailadmin_login"))

    def test_get_shows_confirmation_without_changing_translations(
        self, action, admin_client, translations
    ):
        response = admin_client.get(
            bulk_action_url(action.type, [translations["de"], translations["fr"]])
        )

        assert response.status_code == 200
        assert context_items(response) == [translations["de"], translations["fr"]]
        assert set(
            Translation.objects.values_list("enabled", flat=True).distinct()
        ) == {action.start_enabled}

    @pytest.mark.parametrize(
        ("selected", "already_done", "eligible_count"),
        [(["de"], [], 1), (["de", "es"], [], 2), (["de", "es"], ["es"], 1)],
        ids=["one", "two", "one-of-two-eligible"],
    )
    def test_confirmation_text_matches_eligible_count(
        self,
        action,
        admin_client,
        already_done,
        eligible_count,
        selected,
        translations,
    ):
        Translation.objects.filter(
            target_locale__language_code__in=already_done
        ).update(enabled=action.end_enabled)

        response = admin_client.get(
            bulk_action_url(action.type, [translations[code] for code in selected])
        )

        assert action.confirmation_texts[eligible_count] in response.content.decode()

    def test_post_sets_enabled_on_selected_translations(
        self, action, admin_client, translations
    ):
        response = admin_client.post(
            bulk_action_url(action.type, [translations["de"], translations["fr"]])
        )

        assert response.status_code == 302
        for code, expected in (
            ("de", action.end_enabled),
            ("fr", action.end_enabled),
            ("es", action.start_enabled),
        ):
            translations[code].refresh_from_db()
            assert translations[code].enabled is expected, code

    def test_post_leaves_target_and_source_pages_unchanged(
        self,
        action,
        admin_client,
        django_capture_on_commit_callbacks,
        locale_de,
        locale_es,
        locale_fr,
        test_page_with_translations,
        translations,
    ):
        de_page = target_of(test_page_with_translations, locale_de)
        es_page = target_of(test_page_with_translations, locale_es)
        Page.objects.filter(pk=es_page.pk).update(live=False)
        source = translations["de"].source
        translate_segments(source, locale_de, 1)  # the title
        translate_segments(source, locale_es, 1)
        revision_counts = {
            page.pk: page.revisions.count()
            for page in (de_page, es_page, test_page_with_translations)
        }

        with django_capture_on_commit_callbacks(execute=True):
            response = admin_client.post(
                bulk_action_url(action.type, list(translations.values()))
            )

        assert response.status_code == 302
        for page, live in (
            (de_page, True),
            (es_page, False),
            (test_page_with_translations, True),
        ):
            page.refresh_from_db()
            assert (page.live, page.title) == (live, "Test Page"), page.locale
            assert page.revisions.count() == revision_counts[page.pk], page.locale
        assert not Page.objects.filter(
            translation_key=test_page_with_translations.translation_key,
            locale=locale_fr,
        ).exists()

    @pytest.mark.parametrize("count", [1, 2])
    def test_post_redirects_to_next_with_success_message(
        self, action, admin_client, count, translations
    ):
        next_url = reverse("wagtail_localize_dashboard:manage_translations", args=(1,))
        selected = [translations["de"], translations["es"]][:count]

        response = admin_client.post(bulk_action_url(action.type, selected, next_url))

        assert response.status_code == 302
        assert response.url == next_url
        assert [str(m) for m in get_messages(response.wsgi_request)] == [
            action.success_messages[count]
        ]

    def test_translation_already_in_resulting_state_is_listed_as_ineligible(
        self, action, admin_client, translations
    ):
        Translation.objects.filter(pk=translations["es"].pk).update(
            enabled=action.end_enabled
        )

        response = admin_client.get(
            bulk_action_url(action.type, [translations["de"], translations["es"]])
        )

        assert context_items(response) == [translations["de"]]
        assert context_items(response, "items_ineligible") == [translations["es"]]
        assert action.ineligible_heading in response.content.decode()

    def test_post_leaves_ineligible_translations_untouched(
        self, action, admin_client, translations
    ):
        Translation.objects.filter(pk=translations["es"].pk).update(
            enabled=action.end_enabled
        )

        response = admin_client.post(
            bulk_action_url(action.type, [translations["de"], translations["es"]])
        )

        assert response.status_code == 302
        translations["es"].refresh_from_db()
        assert translations["es"].enabled is action.end_enabled
        assert [str(m) for m in get_messages(response.wsgi_request)] == [
            action.success_messages[1]
        ]

    def test_alias_target_translation_can_be_toggled(
        self, action, admin_client, locale_de, test_page_with_translations, translations
    ):
        Page.objects.filter(
            pk=target_of(test_page_with_translations, locale_de).pk
        ).update(alias_of=test_page_with_translations)

        response = admin_client.post(bulk_action_url(action.type, [translations["de"]]))

        assert response.status_code == 302
        translations["de"].refresh_from_db()
        assert translations["de"].enabled is action.end_enabled

    @pytest.mark.parametrize(
        ("grant", "code"),
        [(grant_submit_translation, "de"), (grant_root_edit, "fr")],
        ids=["page-without-edit-permission", "no-page-without-submit-translation"],
    )
    def test_user_without_permission_is_listed_as_no_access(
        self, action, code, grant, root_page, translations, wagtail_client, wagtail_user
    ):
        grant(wagtail_user, root_page)

        response = wagtail_client.get(
            bulk_action_url(action.type, [translations[code]])
        )

        assert context_items(response) == []
        assert context_items(response, "items_with_no_access") == [translations[code]]

    @pytest.mark.parametrize(
        ("grant", "code"),
        [(grant_root_edit, "de"), (grant_submit_translation, "fr")],
        ids=["page-edit-permission", "no-page-submit-translation"],
    )
    def test_user_with_permission_can_act(
        self, action, code, grant, root_page, translations, wagtail_client, wagtail_user
    ):
        grant(wagtail_user, root_page)

        response = wagtail_client.get(
            bulk_action_url(action.type, [translations[code]])
        )

        assert context_items(response) == [translations[code]]

    def test_post_skips_translations_without_permission(
        self, action, root_page, translations, wagtail_client, wagtail_user
    ):
        grant_submit_translation(wagtail_user, root_page)

        response = wagtail_client.post(
            bulk_action_url(action.type, [translations["de"]])
        )

        assert response.status_code == 302
        translations["de"].refresh_from_db()
        assert translations["de"].enabled is action.start_enabled

    def test_manage_view_after_post_shows_new_syncing_state(
        self, action, admin_client, test_page_with_translations, translations
    ):
        admin_client.post(bulk_action_url(action.type, [translations["de"]]))

        response = admin_client.get(
            reverse(
                "wagtail_localize_dashboard:manage_translations",
                args=(test_page_with_translations.pk,),
            )
        )

        action.assert_listed_state(
            table_row(response.content.decode(), "German")["Syncing"]
        )
