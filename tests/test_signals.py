"""Tests for signal handlers in wagtail-localize-dashboard."""

import logging
from unittest.mock import patch

import polib
import pytest
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import transaction
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from wagtail.models import Locale, Page
from wagtail_localize.models import (
    StringSegment,
    StringTranslation,
    Translation,
    TranslationLog,
    TranslationSource,
)

from tests.helpers import (
    count_translation_progress_calls,
    create_or_replace_page,
    run_on_commit,
)
from tests.models import RichTextSnippet, SampleSnippet
from wagtail_localize_dashboard.models import (
    SnippetTranslationProgress,
    TranslationProgress,
)
from wagtail_localize_dashboard.signals import (
    snippet_deleted_handler,
    snippet_saved_handler,
)

pytestmark = [
    pytest.mark.django_db,
]

User = get_user_model()


@pytest.fixture
def page_with_translation(db):
    """Create a page with translations for testing."""

    # Get or create locales
    en_locale, _ = Locale.objects.get_or_create(
        language_code="en", defaults={"language_code": "en"}
    )
    de_locale, _ = Locale.objects.get_or_create(
        language_code="de", defaults={"language_code": "de"}
    )

    # Get root page
    root = Page.objects.get(depth=1)

    # Create a test page
    page = Page(
        title="Test Page",
        slug="test-page",
        locale=en_locale,
    )
    root.add_child(instance=page)

    return {
        "en_page": page,
        "en_locale": en_locale,
        "de_locale": de_locale,
        "root": root,
    }


@patch.object(transaction, "on_commit", side_effect=lambda func: func())
def test_creating_translation_creates_progress(_mock_on_commit, page_with_translation):
    """Test that creating a translation creates TranslationProgress."""
    en_page = page_with_translation["en_page"]
    de_locale = page_with_translation["de_locale"]

    # Initially, there should be no TranslationProgress
    assert TranslationProgress.objects.count() == 0

    # Create a translation
    translation_source, _ = TranslationSource.get_or_create_from_instance(en_page)
    translation = Translation.objects.create(
        source=translation_source,
        target_locale=de_locale,
        enabled=True,
    )
    translation.save_target(user=None, publish=True)

    # The signal should have created TranslationProgress
    assert TranslationProgress.objects.count() == 1
    progress = TranslationProgress.objects.first()

    assert progress.source_page_id == en_page.id
    assert progress.percent_translated == 0  # No strings translated yet


@patch.object(transaction, "on_commit", side_effect=lambda func: func())
def test_translating_string_updates_progress(_mock_on_commit, page_with_translation):
    """Test that translating a string updates TranslationProgress."""
    en_page = page_with_translation["en_page"]
    de_locale = page_with_translation["de_locale"]

    # Create translation
    translation_source, _ = TranslationSource.get_or_create_from_instance(en_page)
    translation = Translation.objects.create(
        source=translation_source,
        target_locale=de_locale,
        enabled=True,
    )
    translation.save_target(user=None, publish=True)

    # Verify TranslationProgress was created
    assert TranslationProgress.objects.count() == 1
    progress = TranslationProgress.objects.first()
    initial_percent = progress.percent_translated

    # Get a string segment and translate it
    string_segment = translation_source.stringsegment_set.first()
    StringTranslation.objects.create(
        translation_of=string_segment.string,
        locale=de_locale,
        context=string_segment.context,
        data="Deutscher Inhalt",
    )

    # The signal should have updated TranslationProgress
    progress.refresh_from_db()
    assert progress.percent_translated >= initial_percent


@patch.object(transaction, "on_commit", side_effect=lambda func: func())
def test_deleting_translated_page_deletes_progress(
    _mock_on_commit, page_with_translation
):
    """Test that deleting a translated page deletes TranslationProgress."""
    en_page = page_with_translation["en_page"]
    de_locale = page_with_translation["de_locale"]

    # Create translation
    translation_source, _ = TranslationSource.get_or_create_from_instance(en_page)
    translation = Translation.objects.create(
        source=translation_source,
        target_locale=de_locale,
        enabled=True,
    )
    translation.save_target(user=None, publish=True)

    # Verify TranslationProgress was created
    assert TranslationProgress.objects.count() == 1
    progress = TranslationProgress.objects.first()
    translated_page_id = progress.translated_page_id

    # Delete the translated page
    translated_page = Page.objects.get(id=translated_page_id)
    translated_page.delete()

    # CASCADE should have deleted TranslationProgress
    assert TranslationProgress.objects.count() == 0


@patch.object(transaction, "on_commit", side_effect=lambda func: func())
def test_deleting_string_translation_updates_progress(
    _mock_on_commit, page_with_translation
):
    """Test that deleting a StringTranslation updates TranslationProgress."""
    en_page = page_with_translation["en_page"]
    de_locale = page_with_translation["de_locale"]

    # Create translation
    translation_source, _ = TranslationSource.get_or_create_from_instance(en_page)
    translation = Translation.objects.create(
        source=translation_source,
        target_locale=de_locale,
        enabled=True,
    )
    translation.save_target(user=None, publish=True)

    # Translate a string
    string_segment = translation_source.stringsegment_set.first()
    string_translation = StringTranslation.objects.create(
        translation_of=string_segment.string,
        locale=de_locale,
        context=string_segment.context,
        data="Deutscher Inhalt",
    )

    # Get the updated progress
    progress = TranslationProgress.objects.first()
    progress.refresh_from_db()
    percent_before = progress.percent_translated

    # Delete the string translation
    string_translation.delete()

    # The signal should have updated TranslationProgress
    progress.refresh_from_db()
    assert progress.percent_translated <= percent_before


@patch.object(transaction, "on_commit", side_effect=lambda func: func())
def test_deleting_translation_of_page_deletes_progress(
    _mock_on_commit, client, page_with_translation
):
    """Deleting a translation of a page should delete TranslationProgress."""
    # Get the English page.
    en_page = page_with_translation["en_page"]
    # Get locale used in this test.
    de_locale = page_with_translation["de_locale"]

    # Create a translation
    translation_source, _ = TranslationSource.get_or_create_from_instance(en_page)
    translation = Translation.objects.create(
        source=translation_source,
        target_locale=de_locale,
        enabled=True,
    )
    translation.save_target(user=None, publish=True)

    # Verify TranslationProgress was created
    assert TranslationProgress.objects.count() == 1
    progress = TranslationProgress.objects.get(
        source_page_id=en_page.id,
    )
    translated_page = progress.translated_page

    # Create a superuser and login
    User = get_user_model()
    user = User.objects.create_superuser(
        username="admin", email="admin@test.com", password="password"
    )
    client.force_login(user)

    # Delete the translated page via the Wagtail admin
    delete_url = reverse("wagtailadmin_pages:delete", args=[translated_page.id])
    response = client.post(delete_url)

    # The request should succeed (redirect after deletion)
    assert response.status_code == 302, (
        f"Unexpected status code: {response.status_code}"
    )

    # CASCADE should have deleted the TranslationProgress
    assert (
        TranslationProgress.objects.filter(
            source_page_id=en_page.id,
            translated_page_id=translated_page.id,
        ).count()
        == 0
    )


@patch.object(transaction, "on_commit", side_effect=lambda func: func())
def test_saving_page_updates_progress(_mock_on_commit, page_with_translation):
    """Test that saving a page updates TranslationProgress."""
    en_page = page_with_translation["en_page"]
    de_locale = page_with_translation["de_locale"]

    # Create translation
    translation_source, _ = TranslationSource.get_or_create_from_instance(en_page)
    translation = Translation.objects.create(
        source=translation_source,
        target_locale=de_locale,
        enabled=True,
    )
    translation.save_target(user=None, publish=True)

    # Verify TranslationProgress was created
    assert TranslationProgress.objects.count() == 1

    percent_before = TranslationProgress.objects.first().percent_translated

    # Save the page (triggers signal)
    en_page.title = "Updated Test Page"
    en_page.save()

    # The signal should have updated TranslationProgress
    progress = TranslationProgress.objects.first()
    assert progress is not None
    assert progress.percent_translated == percent_before


@patch.object(transaction, "on_commit", side_effect=lambda func: func())
def test_saving_page_creates_progress(_mock_on_commit, page_with_translation):
    """Test that saving a page creates TranslationProgress if none exists."""
    en_page = page_with_translation["en_page"]
    de_locale = page_with_translation["de_locale"]

    # Create translation
    translation_source, _ = TranslationSource.get_or_create_from_instance(en_page)
    translation = Translation.objects.create(
        source=translation_source,
        target_locale=de_locale,
        enabled=True,
    )
    translation.save_target(user=None, publish=True)

    # Verify TranslationProgress was created
    assert TranslationProgress.objects.count() == 1

    # Delete the TranslationProgress
    TranslationProgress.objects.all().delete()

    # Save the page (triggers signal)
    en_page.title = "Updated Test Page"
    en_page.save()

    # The signal should have created a TranslationProgress object
    assert TranslationProgress.objects.count() == 1
    progress = TranslationProgress.objects.first()
    assert progress.source_page == en_page


@patch.object(transaction, "on_commit", side_effect=lambda func: func())
def test_translation_chain_creates_correct_progress(
    _mock_on_commit, page_with_translation
):
    """Test translation chain (A→B→C) creates correct TranslationProgress."""
    en_page = page_with_translation["en_page"]
    de_locale = page_with_translation["de_locale"]

    # Create French locale
    fr_locale, _ = Locale.objects.get_or_create(language_code="fr")

    # Create German translation (A→B)
    translation_source_en, _ = TranslationSource.get_or_create_from_instance(en_page)
    translation_de = Translation.objects.create(
        source=translation_source_en,
        target_locale=de_locale,
        enabled=True,
    )
    translation_de.save_target(user=None, publish=True)
    de_page = Page.objects.get(
        locale=de_locale, translation_key=en_page.translation_key
    )

    # Create French translation from German page (B→C)
    translation_source_de, _ = TranslationSource.get_or_create_from_instance(de_page)
    translation_fr = Translation.objects.create(
        source=translation_source_de,
        target_locale=fr_locale,
        enabled=True,
    )
    translation_fr.save_target(user=None, publish=True)
    fr_page = Page.objects.get(
        locale=fr_locale, translation_key=en_page.translation_key
    )

    # Both German and French should have progress records referencing the original English page

    # Check German progress
    de_progress = TranslationProgress.objects.filter(
        source_page_id=en_page.id, translated_page_id=de_page.id
    ).first()
    assert de_progress is not None

    # Check French progress - should also reference English as source
    fr_progress = TranslationProgress.objects.filter(
        source_page_id=en_page.id, translated_page_id=fr_page.id
    ).first()
    assert fr_progress is not None


@patch.object(transaction, "on_commit", side_effect=lambda func: func())
def test_page_with_no_translations_creates_no_progress(
    _mock_on_commit, page_with_translation
):
    """Test that a page with no translations creates no TranslationProgress."""
    root = page_with_translation["root"]
    en_locale = page_with_translation["en_locale"]

    # Create a standalone page
    standalone_page = Page(
        title="Standalone Page",
        slug="standalone",
        locale=en_locale,
    )
    root.add_child(instance=standalone_page)
    standalone_page.save()

    # Verify no TranslationProgress was created
    assert (
        TranslationProgress.objects.filter(source_page_id=standalone_page.id).count()
        == 0
    )


@patch.object(transaction, "on_commit", side_effect=lambda func: func())
@override_settings(WAGTAIL_LOCALIZE_DASHBOARD_AUTO_UPDATE=False)
def test_signal_respects_auto_update_setting(_mock_on_commit, page_with_translation):
    """Test that signals respect the AUTO_UPDATE setting."""
    en_page = page_with_translation["en_page"]
    de_locale = page_with_translation["de_locale"]

    # Create translation with AUTO_UPDATE=False
    translation_source, _ = TranslationSource.get_or_create_from_instance(en_page)
    translation = Translation.objects.create(
        source=translation_source,
        target_locale=de_locale,
        enabled=True,
    )
    translation.save_target(user=None, publish=True)

    # No TranslationProgress should be created when AUTO_UPDATE=False
    assert TranslationProgress.objects.count() == 0


@patch.object(transaction, "on_commit", side_effect=lambda func: func())
@override_settings(WAGTAIL_LOCALIZE_DASHBOARD_ENABLED=False)
def test_signal_respects_enabled_setting(_mock_on_commit, page_with_translation):
    """Test that signals respect the AUTO_UPDATE setting."""
    en_page = page_with_translation["en_page"]
    de_locale = page_with_translation["de_locale"]

    # Create translation with AUTO_UPDATE=False
    translation_source, _ = TranslationSource.get_or_create_from_instance(en_page)
    translation = Translation.objects.create(
        source=translation_source,
        target_locale=de_locale,
        enabled=True,
    )
    translation.save_target(user=None, publish=True)

    # No TranslationProgress should be created when ENABLED=False
    assert TranslationProgress.objects.count() == 0


@patch.object(transaction, "on_commit", side_effect=lambda func: func())
def test_signal_uses_page_content_type_not_specific(
    _mock_on_commit, page_with_translation
):
    """Test that signals use Page content type, not specific subclass."""
    en_page = page_with_translation["en_page"]
    de_locale = page_with_translation["de_locale"]

    # Create translation
    translation_source, _ = TranslationSource.get_or_create_from_instance(en_page)
    translation = Translation.objects.create(
        source=translation_source,
        target_locale=de_locale,
        enabled=True,
    )
    translation.save_target(user=None, publish=True)

    # Verify that progress was created with ForeignKey relationships
    progress = TranslationProgress.objects.first()

    assert progress.source_page_id == en_page.id
    assert isinstance(progress.translated_page, Page)


@patch.object(transaction, "on_commit", side_effect=lambda func: func())
def test_page_saved_signal_skips_raw_save(
    _mock_on_commit, page_with_translation, tmp_path
):
    """
    Saving a Page with raw=True should NOT trigger the signal handler.

    The post_save signal's "raw" argument from Django's documentation:
      A boolean; True if the model is saved exactly as presented (i.e. when
      loading a fixture). One should not query/modify other records in the
      database as the database might not be in a consistent state yet.
    """
    # Get the English page.
    en_page = page_with_translation["en_page"]
    # Get locale used in this test.
    de_locale = page_with_translation["de_locale"]

    # Create a translation.
    translation_source, _ = TranslationSource.get_or_create_from_instance(en_page)
    translation = Translation.objects.create(
        source=translation_source,
        target_locale=de_locale,
        enabled=True,
    )
    translation.save_target(user=None, publish=True)

    # Verify a TranslationProgress object was created.
    assert TranslationProgress.objects.count() == 1

    # Export to fixture including revisions
    fixture_file = tmp_path / "test_fixture.json"
    with open(fixture_file, "w") as f:
        call_command(
            "dumpdata",
            "wagtailcore.page",
            "wagtailcore.revision",
            format="json",
            stdout=f,
        )

    # Remember the page ID before deleting
    en_page_id = en_page.id

    # Delete the pages and wagtail-localize tables to simulate a script.
    en_page.delete()
    TranslationSource.objects.all().delete()
    Translation.objects.all().delete()
    # Delete all TranslationProgress objects.
    TranslationProgress.objects.all().delete()

    # Load the fixture - with raw=True, the signal handler should skip processing
    # This should not raise an error even though wagtail-localize tables don't exist.
    call_command("loaddata", str(fixture_file))

    # No TranslationProgress objects should have been created during fixture load
    assert TranslationProgress.objects.count() == 0

    # Get the page again from database (it was reloaded from fixture)
    reloaded_page = Page.objects.get(id=en_page_id)

    # Saving the reloaded_page should create the TranslationProgress object again.
    reloaded_page.save()
    assert TranslationProgress.objects.filter(source_page_id=reloaded_page.id).exists()


@patch.object(transaction, "on_commit", side_effect=lambda func: func())
def test_uploading_po_file_updates_page_translation_data(
    _mock_on_commit, client, page_with_translation, locale_fr
):
    """Uploading a .po file for a translation should update TranslationProgress data."""
    # Get the English page from the fixture
    en_page = page_with_translation["en_page"]

    # Create a translation
    translation_source, _ = TranslationSource.get_or_create_from_instance(en_page)
    translation = Translation.objects.create(
        source=translation_source,
        target_locale=locale_fr,
        enabled=True,
    )
    translation.save_target(user=None, publish=True)

    # Verify TranslationProgress was created with initial progress
    assert TranslationProgress.objects.count() == 1
    translation_data = TranslationProgress.objects.get(source_page=en_page)
    assert translation_data.percent_translated < 100

    # Create a superuser and login
    User = get_user_model()
    user = User.objects.create_superuser(
        username="admin", email="admin@test.com", password="password"
    )
    client.force_login(user)

    # Create a PO file with translations for the page
    po = polib.POFile(wrapwidth=200)
    po.metadata = {
        "POT-Creation-Date": str(timezone.now()),
        "MIME-Version": "1.0",
        "Content-Type": "text/plain; charset=utf-8",
        "X-WagtailLocalize-TranslationID": str(translation.uuid),
    }

    # Get translatable string segments from the translation
    string_segments = translation_source.stringsegment_set.all()
    assert string_segments.count() > 0, "No string segments found for translation"

    # Add translations for all string segments to the PO file
    for segment in string_segments:
        po.append(
            polib.POEntry(
                msgid=segment.string.data,
                msgctxt=segment.context.path,
                msgstr=f"Traduction française: {segment.string.data}",
            )
        )

    # Make sure (just before uploading the .po file) that the percent translated is less than 100%.
    translation_data.refresh_from_db()
    assert translation_data.percent_translated < 100

    # Upload the PO file via the wagtail-localize upload_pofile view
    upload_url = reverse("wagtail_localize:upload_pofile", args=[translation.id])
    fr_page = translation.get_target_instance()
    response = client.post(
        upload_url,
        {
            "file": SimpleUploadedFile(
                "translations.po",
                str(po).encode("utf-8"),
                content_type="text/x-gettext-translation",
            ),
            "next": reverse("wagtailadmin_pages:edit", args=[fr_page.id]),
        },
    )

    # The request should succeed (redirect after upload)
    assert response.status_code == 302, (
        f"Unexpected status code: {response.status_code}"
    )

    # The signal should have updated TranslationProgress: all fields should now be translated.
    translation_data.refresh_from_db()
    assert translation_data.percent_translated == 100


@patch.object(transaction, "on_commit", side_effect=lambda func: func())
@patch("wagtail_localize_dashboard.utils.create_page_translation_progress")
def test_snippet_translation_does_not_call_create_page_translation_progress(
    _mock_create_page_translation_progress, _mock_on_commit, locale_en, locale_fr
):
    """Test that creating a translation for a snippet does NOT call create_page_translation_data."""
    # Create a snippet (non-page object)
    snippet = SampleSnippet.objects.create(
        locale=locale_en,
        heading="Test Heading",
        desc="Test Description",
    )

    # Create a TranslationSource for the snippet
    translation_source, _ = TranslationSource.get_or_create_from_instance(snippet)

    # Create a Translation for the snippet
    translation = Translation.objects.create(
        source=translation_source,
        target_locale=locale_fr,
        enabled=True,
    )
    translation.save_target(user=None, publish=True)

    # Verify that create_page_translation_progress was NOT called
    _mock_create_page_translation_progress.assert_not_called()


@patch.object(transaction, "on_commit", side_effect=lambda func: func())
@patch("wagtail_localize_dashboard.utils.create_page_translation_progress")
def test_snippet_string_translation_does_not_call_create_page_translation_progress(
    _mock_create_page_translation_progress, _mock_on_commit, locale_en, locale_fr
):
    """Test that creating a StringTranslation for a snippet does NOT call create_page_translation_data."""
    # Create a snippet (non-page object)
    snippet = SampleSnippet.objects.create(
        locale=locale_en,
        heading="Test Heading",
        desc="Test Description",
    )

    # Create a TranslationSource for the snippet
    translation_source, _ = TranslationSource.get_or_create_from_instance(snippet)

    # Create a Translation for the snippet
    translation = Translation.objects.create(
        source=translation_source,
        target_locale=locale_fr,
        enabled=True,
    )
    translation.save_target(user=None, publish=True)

    # Get a string segment from the translation source
    string_segment = translation_source.stringsegment_set.first()
    assert string_segment is not None, (
        "No string segments found for snippet translation"
    )

    # Reset the mock to clear any calls from the translation creation
    _mock_create_page_translation_progress.reset_mock()

    # Create a StringTranslation for the snippet
    StringTranslation.objects.create(
        translation_of=string_segment.string,
        locale=locale_fr,
        context=string_segment.context,
        data="Titre français",
    )

    # Verify that create_page_translation_progress was NOT called
    _mock_create_page_translation_progress.assert_not_called()


@patch.object(transaction, "on_commit", side_effect=lambda func: func())
@patch("wagtail_localize_dashboard.utils.create_page_translation_progress")
def test_snippet_string_translation_deletion_does_not_call_create_page_translation_progress(
    _mock_create_page_translation_progress, _mock_on_commit, locale_en, locale_fr
):
    """Test that deleting a StringTranslation for a snippet does NOT call create_page_translation_data."""
    # Create a snippet (non-page object)
    snippet = SampleSnippet.objects.create(
        locale=locale_en,
        heading="Test Heading",
        desc="Test Description",
    )

    # Create a TranslationSource for the snippet
    translation_source, _ = TranslationSource.get_or_create_from_instance(snippet)

    # Create a Translation for the snippet
    translation = Translation.objects.create(
        source=translation_source,
        target_locale=locale_fr,
        enabled=True,
    )
    translation.save_target(user=None, publish=True)

    # Get a string segment from the translation source
    string_segment = translation_source.stringsegment_set.first()
    assert string_segment is not None, (
        "No string segments found for snippet translation"
    )

    # Create a StringTranslation for the snippet
    string_translation = StringTranslation.objects.create(
        translation_of=string_segment.string,
        locale=locale_fr,
        context=string_segment.context,
        data="Titre français",
    )

    # Reset the mock to clear any calls from the translation creation
    _mock_create_page_translation_progress.reset_mock()

    # Delete the StringTranslation
    string_translation.delete()

    # Verify that create_page_translation_progress was NOT called
    _mock_create_page_translation_progress.assert_not_called()


@patch.object(transaction, "on_commit", side_effect=lambda func: func())
@patch("wagtail_localize_dashboard.utils.create_page_translation_progress")
def test_snippet_translation_source_save_does_not_call_create_page_translation_progress(
    _mock_create_page_translation_progress, _mock_on_commit, locale_en
):
    """Test that saving a TranslationSource for a snippet does NOT call create_page_translation_data."""
    # Create a snippet (non-page object)
    snippet = SampleSnippet.objects.create(
        locale=locale_en,
        heading="Test Heading",
        desc="Test Description",
    )

    # Reset the mock before creating translation source
    _mock_create_page_translation_progress.reset_mock()

    # Create a TranslationSource for the snippet
    translation_source, _ = TranslationSource.get_or_create_from_instance(snippet)

    # Verify that create_page_translation_progress was NOT called
    _mock_create_page_translation_progress.assert_not_called()

    # Now update the snippet and update the translation source
    snippet.heading = "Updated Heading"
    snippet.save()

    # Reset the mock again
    _mock_create_page_translation_progress.reset_mock()

    # Update the translation source
    translation_source.update_from_db()

    # Verify that create_page_translation_progress was NOT called
    _mock_create_page_translation_progress.assert_not_called()


@patch.object(transaction, "on_commit", side_effect=lambda func: func())
@override_settings(WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"])
@patch("wagtail_localize_dashboard.signals.create_snippet_translation_progress")
def test_tracked_snippet_translation_calls_create_snippet_translation_progress(
    mock_create_snippet_progress, mock_on_commit, locale_en, locale_fr
):
    """Test that saving a Translation for a tracked snippet calls create_snippet_translation_progress."""
    snippet = SampleSnippet.objects.create(
        locale=locale_en, heading="Test Heading", desc="Test Description"
    )
    translation_source, _ = TranslationSource.get_or_create_from_instance(snippet)
    Translation.objects.create(
        source=translation_source,
        target_locale=locale_fr,
        enabled=True,
    )

    # Called by both translation_source_saved_handler and translation_saved_handler
    mock_create_snippet_progress.assert_called_with(snippet, only_locale=locale_fr.pk)
    assert mock_create_snippet_progress.call_count == 2


@patch.object(transaction, "on_commit", side_effect=lambda func: func())
@override_settings(WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"])
@patch("wagtail_localize_dashboard.signals.create_snippet_translation_progress")
def test_tracked_snippet_string_translation_calls_create_snippet_translation_progress(
    mock_create_snippet_progress, mock_on_commit, locale_en, locale_fr
):
    """Test that a StringTranslation for a tracked snippet calls create_snippet_translation_progress."""
    snippet = SampleSnippet.objects.create(
        locale=locale_en, heading="Test Heading", desc="Test Description"
    )
    translation_source, _ = TranslationSource.get_or_create_from_instance(snippet)
    Translation.objects.create(
        source=translation_source,
        target_locale=locale_fr,
        enabled=True,
    )

    string_segment = translation_source.stringsegment_set.first()
    assert string_segment is not None, "No string segments found for snippet"

    mock_create_snippet_progress.reset_mock()

    StringTranslation.objects.create(
        translation_of=string_segment.string,
        locale=locale_fr,
        context=string_segment.context,
        data="French translation",
    )

    mock_create_snippet_progress.assert_called_once_with(
        snippet, only_locale=locale_fr.pk
    )


@patch.object(transaction, "on_commit", side_effect=lambda func: func())
def test_snippet_saved_handler_calls_create_snippet_translation_progress(
    mock_on_commit, locale_en
):
    """snippet_saved_handler calls create_snippet_translation_progress for the original snippet."""
    snippet = SampleSnippet.objects.create(locale=locale_en, heading="Test Heading")

    with patch(
        "wagtail_localize_dashboard.signals.create_snippet_translation_progress"
    ) as mock_fn:
        snippet_saved_handler(SampleSnippet, snippet, created=False)
        mock_fn.assert_called_once_with(snippet)


@patch.object(transaction, "on_commit", side_effect=lambda func: func())
@override_settings(WAGTAIL_LOCALIZE_DASHBOARD_AUTO_UPDATE=False)
def test_snippet_saved_handler_respects_auto_update_setting(mock_on_commit, locale_en):
    """snippet_saved_handler does nothing when AUTO_UPDATE=False."""
    snippet = SampleSnippet.objects.create(locale=locale_en, heading="Test")

    with patch(
        "wagtail_localize_dashboard.signals.create_snippet_translation_progress"
    ) as mock_fn:
        snippet_saved_handler(SampleSnippet, snippet, created=False)
        mock_fn.assert_not_called()


def test_snippet_deleted_handler_removes_translated_progress(locale_en, locale_de):
    """snippet_deleted_handler removes progress records where snippet is the translated object."""
    source = SampleSnippet.objects.create(locale=locale_en, heading="Source")
    translated = SampleSnippet.objects.create(locale=locale_de, heading="Translated")
    ct = ContentType.objects.get_for_model(SampleSnippet)

    SnippetTranslationProgress.objects.create(
        content_type=ct,
        source_object_id=source.pk,
        translated_object_id=translated.pk,
        translated_locale=locale_de,
        percent_translated=50,
    )

    assert SnippetTranslationProgress.objects.count() == 1

    snippet_deleted_handler(SampleSnippet, translated)

    assert SnippetTranslationProgress.objects.count() == 0


def test_snippet_deleted_handler_removes_source_progress(locale_en, locale_de):
    """snippet_deleted_handler removes progress records where snippet is the source object."""
    source = SampleSnippet.objects.create(locale=locale_en, heading="Source")
    translated = SampleSnippet.objects.create(locale=locale_de, heading="Translated")
    ct = ContentType.objects.get_for_model(SampleSnippet)

    SnippetTranslationProgress.objects.create(
        content_type=ct,
        source_object_id=source.pk,
        translated_object_id=translated.pk,
        translated_locale=locale_de,
        percent_translated=50,
    )

    snippet_deleted_handler(SampleSnippet, source)

    assert SnippetTranslationProgress.objects.count() == 0


@patch.object(transaction, "on_commit", side_effect=lambda func: func())
@override_settings(WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"])
@patch("wagtail_localize_dashboard.signals.create_snippet_translation_progress")
def test_tracked_snippet_string_translation_deletion_calls_create_snippet_progress(
    mock_create_snippet_progress, mock_on_commit, locale_en, locale_fr
):
    """Deleting a StringTranslation for a tracked snippet calls create_snippet_translation_progress."""
    snippet = SampleSnippet.objects.create(
        locale=locale_en, heading="Test Heading", desc="Test Description"
    )
    translation_source, _ = TranslationSource.get_or_create_from_instance(snippet)
    Translation.objects.create(
        source=translation_source, target_locale=locale_fr, enabled=True
    )
    string_segment = translation_source.stringsegment_set.first()
    assert string_segment is not None

    string_translation = StringTranslation.objects.create(
        translation_of=string_segment.string,
        locale=locale_fr,
        context=string_segment.context,
        data="French translation",
    )
    mock_create_snippet_progress.reset_mock()

    string_translation.delete()

    mock_create_snippet_progress.assert_called_once_with(
        snippet, only_locale=locale_fr.pk
    )


@patch.object(transaction, "on_commit", side_effect=lambda func: func())
@override_settings(WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"])
@patch("wagtail_localize_dashboard.signals.create_snippet_translation_progress")
def test_tracked_snippet_translation_source_save_calls_create_snippet_progress(
    mock_create_snippet_progress, mock_on_commit, locale_en
):
    """Saving a TranslationSource for a tracked snippet calls create_snippet_translation_progress."""
    snippet = SampleSnippet.objects.create(
        locale=locale_en, heading="Test Heading", desc="Test Description"
    )
    mock_create_snippet_progress.reset_mock()

    TranslationSource.get_or_create_from_instance(snippet)

    mock_create_snippet_progress.assert_called_once_with(snippet)


@patch.object(transaction, "on_commit", side_effect=lambda func: func())
def test_snippet_saved_handler_finds_original_when_translated_saved(
    mock_on_commit, locale_en, locale_de
):
    """snippet_saved_handler calls create_snippet_translation_progress with the original, not the translated instance."""
    original = SampleSnippet.objects.create(locale=locale_en, heading="Original")
    translated = original.copy_for_translation(locale_de)
    translated.save()
    assert original.pk < translated.pk  # original has the lower pk

    with patch(
        "wagtail_localize_dashboard.signals.create_snippet_translation_progress"
    ) as mock_fn:
        snippet_saved_handler(SampleSnippet, translated, created=False)
        mock_fn.assert_called_once_with(original)


@patch.object(transaction, "on_commit", side_effect=lambda func: func())
def test_snippet_saved_handler_does_nothing_when_no_original(mock_on_commit):
    """snippet_saved_handler does not call create_snippet_translation_progress when no DB record has that translation_key."""
    import uuid

    dummy = SampleSnippet()
    dummy.translation_key = uuid.uuid4()

    with patch(
        "wagtail_localize_dashboard.signals.create_snippet_translation_progress"
    ) as mock_fn:
        snippet_saved_handler(SampleSnippet, dummy, created=False)
        mock_fn.assert_not_called()


@override_settings(
    WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.RichTextSnippet"]
)
@patch.object(transaction, "on_commit", side_effect=lambda func: func())
def test_repeated_rich_text_does_not_break_the_handler(
    mock_on_commit, caplog, locale_en, locale_de
):
    """Repeated text in one rich text field must not break the progress handlers."""
    snippet = RichTextSnippet.objects.create(
        locale=locale_en, body="<p>Hello</p><p>World</p><p>Hello</p>"
    )
    source, __ = TranslationSource.get_or_create_from_instance(snippet)
    segments = StringSegment.objects.filter(source=source)
    assert segments.count() == 3
    assert segments.values("context_id", "string_id").distinct().count() == 2, (
        "two of these three segments must share a (context, string) pair"
    )

    translation, _ = Translation.objects.get_or_create(
        source=source, target_locale=locale_de
    )
    translation.save_target(publish=True)

    with caplog.at_level(logging.ERROR, logger="wagtail_localize_dashboard.signals"):
        for segment in segments:
            StringTranslation.objects.update_or_create(
                translation_of_id=segment.string_id,
                context_id=segment.context_id,
                locale=locale_de,
                defaults={"data": f"DE {segment.string.data}"},
            )

    assert caplog.records == [], [r.getMessage() for r in caplog.records]
    assert SnippetTranslationProgress.objects.filter(
        source_object_id=snippet.pk, translated_locale=locale_de
    ).exists()


@run_on_commit
def test_saving_a_target_rebuilds_only_that_locale_progress(
    _mock_on_commit, test_page, locale_de, locale_es
):
    import wagtail_localize_dashboard.signals as dashboard_signals

    for locale in (locale_de, locale_es):
        test_page.copy_for_translation(locale, copy_parents=True).save()
    de_page = Page.objects.get(
        translation_key=test_page.translation_key, locale=locale_de
    )

    # Saving the de_page must recalculate the de_locale's percentages for the test_page.
    create_page_translation_progress_calls_pages = []
    create_page_translation_progress_calls_kws = []

    def record_call(page, **kwargs):
        create_page_translation_progress_calls_pages.append(page)
        create_page_translation_progress_calls_kws.append(kwargs)

    with patch.object(
        dashboard_signals, "create_page_translation_progress", record_call
    ):
        de_page.title = "Geaenderter Titel"
        de_page.save()

    assert create_page_translation_progress_calls_pages, (
        "saving a target must call create_page_translation_progress()"
    )
    assert create_page_translation_progress_calls_pages == [test_page], (
        "saving a target must rebuild the progress for the relevant page"
    )
    assert create_page_translation_progress_calls_kws, (
        "saving a target must call create_page_translation_progress()"
    )
    assert create_page_translation_progress_calls_kws == [
        {"only_locale": locale_de.pk}
    ], "saving a target must rebuild only that target's progress"


@run_on_commit
def test_saving_the_source_rebuilds_every_locale_progress(
    _mock_on_commit, test_page, locale_de, locale_es
):
    import wagtail_localize_dashboard.signals as dashboard_signals

    for locale in (locale_de, locale_es):
        test_page.copy_for_translation(locale, copy_parents=True).save()

    create_page_translation_progress_calls_kws = []

    def record_call(page, **kwargs):
        create_page_translation_progress_calls_kws.append(kwargs)

    with patch.object(
        dashboard_signals, "create_page_translation_progress", record_call
    ):
        test_page.title = "Changed title"
        test_page.save()

    assert create_page_translation_progress_calls_kws, (
        "saving a source must call create_page_translation_progress()"
    )
    # only_locale=None is how the builder is asked for every locale; naming the
    # locales instead would only rebuild the ones named here.
    assert create_page_translation_progress_calls_kws == [{"only_locale": None}], (
        "saving a source page must rebuild progress for all translations"
    )


@pytest.mark.django_db(transaction=True)
def test_a_rollback_leaves_nothing_queued(home_page):
    """A rolled-back transaction must leak nothing into the next one."""
    from django.db import transaction as db_transaction

    page = create_or_replace_page(home_page, "rollback-me")

    with count_translation_progress_calls() as translation_progress_calls:
        with db_transaction.atomic():
            page.title = "This translation is being rolled back"
            page.save()
            db_transaction.set_rollback(True)

        assert translation_progress_calls["n"] == 0, (
            "a rolled-back save must not rebuild"
        )

        with db_transaction.atomic():
            page.title = "Committed"
            page.save()

    assert translation_progress_calls["n"] == 1, (
        f"the transaction after a rollback did {translation_progress_calls['n']} rebuilds, expected "
        "exactly 1; anything more means the rolled-back transaction left work "
        "behind, anything less means it left something that suppressed this one"
    )


@pytest.mark.django_db(transaction=True)
def test_autocommit_saves_still_rebuild(home_page):
    """on_commit fires immediately outside an atomic block."""
    page = create_or_replace_page(home_page, "autocommit-me")

    with count_translation_progress_calls() as translation_progress_calls:
        page.title = "Saved outside atomic"
        page.save()

    assert translation_progress_calls["n"] >= 1


@pytest.mark.parametrize(
    "handler_name",
    [
        "translation_saved_handler",
        "string_translation_saved_handler",
        "translation_log_saved_handler",
    ],
)
@run_on_commit
def test_translation_handlers_narrow_to_their_locale(
    _mock_on_commit, handler_name, test_page, locale_de, locale_es
):
    """Each handler rebuilds only the locale its signal carried."""
    import wagtail_localize_dashboard.signals as dashboard_signals

    for locale in (locale_de, locale_es):
        test_page.copy_for_translation(locale, copy_parents=True).save()

    source, __ = TranslationSource.get_or_create_from_instance(test_page)

    create_page_translation_progress_calls_kws = []

    def record_call(page, **kwargs):
        create_page_translation_progress_calls_kws.append(kwargs)

    with patch.object(
        dashboard_signals, "create_page_translation_progress", record_call
    ):
        if handler_name == "translation_saved_handler":
            Translation.objects.get_or_create(source=source, target_locale=locale_de)
        elif handler_name == "string_translation_saved_handler":
            Translation.objects.get_or_create(source=source, target_locale=locale_de)
            segment = (
                StringSegment.objects.filter(source=source).order_by("order").first()
            )
            # Only the StringTranslation save is under test; the Translation
            # above had to exist first.
            create_page_translation_progress_calls_kws.clear()
            StringTranslation.objects.update_or_create(
                translation_of=segment.string,
                context=segment.context,
                locale=locale_de,
                defaults={"data": "DE text"},
            )
        elif handler_name == "translation_log_saved_handler":
            Translation.objects.get_or_create(source=source, target_locale=locale_de)
            create_page_translation_progress_calls_kws.clear()
            TranslationLog.objects.create(source=source, locale=locale_de)

    assert create_page_translation_progress_calls_kws, f"{handler_name} queued nothing"
    assert all(
        kw.get("only_locale") == locale_de.pk
        for kw in create_page_translation_progress_calls_kws
    ), (
        f"{handler_name} rebuilt {create_page_translation_progress_calls_kws}, "
        f"expected only_locale={locale_de.pk}"
    )


@run_on_commit
def test_deleting_a_string_translation_narrows_to_its_locale(
    _mock_on_commit, test_page, locale_de, locale_es
):
    """pre_delete must only rebuild for the deleted translation's locale."""
    import wagtail_localize_dashboard.signals as dashboard_signals

    for locale in (locale_de, locale_es):
        test_page.copy_for_translation(locale, copy_parents=True).save()

    source, __ = TranslationSource.get_or_create_from_instance(test_page)
    Translation.objects.get_or_create(source=source, target_locale=locale_de)
    segment = StringSegment.objects.filter(source=source).order_by("order").first()
    string_translation, __ = StringTranslation.objects.update_or_create(
        translation_of=segment.string,
        context=segment.context,
        locale=locale_de,
        defaults={"data": "DE text"},
    )

    create_page_translation_progress_calls_kws = []

    def record_call(page, **kwargs):
        create_page_translation_progress_calls_kws.append(kwargs)

    with patch.object(
        dashboard_signals, "create_page_translation_progress", record_call
    ):
        string_translation.delete()

    assert create_page_translation_progress_calls_kws, (
        "deleting a StringTranslation queued nothing"
    )
    assert all(
        kw.get("only_locale") == locale_de.pk
        for kw in create_page_translation_progress_calls_kws
    ), create_page_translation_progress_calls_kws


@override_settings(WAGTAIL_LOCALIZE_DASHBOARD_TRACKED_SNIPPETS=["tests.SampleSnippet"])
@run_on_commit
def test_snippet_handlers_narrow_to_their_locale(
    _mock_on_commit, sample_snippet, sample_snippet_de, locale_de
):
    """Snippet handlers branch must pass only_locale when non-source objects are updated."""
    import wagtail_localize_dashboard.signals as dashboard_signals

    source, __ = TranslationSource.get_or_create_from_instance(sample_snippet)
    Translation.objects.get_or_create(source=source, target_locale=locale_de)
    segment = StringSegment.objects.filter(source=source).order_by("order").first()
    assert segment is not None, "the snippet must have a translatable segment"

    create_snippet_translation_progress_calls_kws = []

    def record_call(snippet, **kwargs):
        create_snippet_translation_progress_calls_kws.append(kwargs)

    with patch.object(
        dashboard_signals, "create_snippet_translation_progress", record_call
    ):
        StringTranslation.objects.update_or_create(
            translation_of=segment.string,
            context=segment.context,
            locale=locale_de,
            defaults={"data": "DE snippet text"},
        )

    assert create_snippet_translation_progress_calls_kws, (
        "saving a snippet StringTranslation queued nothing"
    )
    assert all(
        kw.get("only_locale") == locale_de.pk
        for kw in create_snippet_translation_progress_calls_kws
    ), create_snippet_translation_progress_calls_kws


@run_on_commit
def test_saving_a_translation_source_rebuilds_every_locale(
    _mock_on_commit, test_page, locale_de, locale_es
):
    import wagtail_localize_dashboard.signals as dashboard_signals

    for locale in (locale_de, locale_es):
        test_page.copy_for_translation(locale, copy_parents=True).save()

    source, __ = TranslationSource.get_or_create_from_instance(test_page)

    create_page_translation_progress_calls_kws = []

    def record_call(page, **kwargs):
        create_page_translation_progress_calls_kws.append(kwargs)

    with patch.object(
        dashboard_signals, "create_page_translation_progress", record_call
    ):
        source.save()

    assert create_page_translation_progress_calls_kws, (
        "saving a TranslationSource queued nothing"
    )
    assert all(
        kw.get("only_locale") is None
        for kw in create_page_translation_progress_calls_kws
    ), (
        "translation_source_saved_handler narrowed to "
        f"{create_page_translation_progress_calls_kws}; a source revision "
        "changes what every locale is compared against"
    )
