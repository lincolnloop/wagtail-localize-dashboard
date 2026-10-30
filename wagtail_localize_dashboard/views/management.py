"""Views for managing the translations of a single page."""

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext
from django.views.decorators.cache import never_cache
from django.views.defaults import permission_denied
from wagtail.admin.ui import tables
from wagtail.admin.views.bulk_action import BulkAction
from wagtail.admin.views.generic.base import BaseListingView, BaseObjectMixin
from wagtail.admin.widgets.button import HeaderButton
from wagtail.models import Locale, Page
from wagtail_localize.models import (
    StringSegment,
    StringTranslation,
    Translation,
    TranslationSource,
)

from wagtail_localize_dashboard.utils import _count_published


def get_target_page(translation):
    """The translated page, or None if it hasn't been created yet."""
    return Page.objects.filter(
        translation_key=translation.source.object_id,
        locale_id=translation.target_locale_id,
    ).first()


def progress_html(done, total):
    percent = int(done / total * 100) if total else 100
    if percent == 100:
        classname = "text-success"
    elif percent >= 80:
        classname = "text-warning"
    else:
        classname = "text-danger"
    return format_html(
        '<span class="{}">{}</span>',
        classname,
        _("%(percent)s%% (%(done)s of %(total)s)")
        % {"percent": percent, "done": done, "total": total},
    )


@method_decorator(never_cache, name="dispatch")
class PageTranslationsManageView(BaseObjectMixin, BaseListingView):
    model = Page
    paginate_by = None
    template_name = "wagtail_localize_dashboard/manage.html"
    page_title = gettext_lazy("Manage Translations")
    breadcrumbs_items = BaseListingView.breadcrumbs_items + [
        {
            "url": reverse_lazy("wagtail_localize_dashboard:dashboard"),
            "label": _("Translations"),
        }
    ]
    header_icon = "wagtail-localize-language"

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.source = TranslationSource.objects.get_for_instance_or_none(self.object)

    def dispatch(self, request, *args, **kwargs):
        if self.source is None:
            # Translated pages and aliases have no source; the original is the
            # lowest id for the translation key, as on the dashboard.
            original = (
                Page.objects.filter(translation_key=self.object.translation_key)
                .order_by("pk")
                .first()
            )
            if original.pk != self.object.pk:
                return redirect(
                    "wagtail_localize_dashboard:manage_translations", original.pk
                )
            raise Http404
        if not self.get_queryset().exists():
            raise Http404
        user = request.user
        if not (
            user.has_perm("wagtail_localize.submit_translation")
            and self.object.permissions_for_user(user).can_edit()
        ):
            # Not raised: Wagtail's admin would turn it into a redirect home.
            return permission_denied(request, PermissionDenied())
        return super().dispatch(request, *args, **kwargs)

    def get_page_subtitle(self):
        return self.object.title

    @cached_property
    def header_buttons(self):
        page = self.object
        buttons = [
            HeaderButton(
                label=_("Edit %(locale)s Page")
                % {"locale": page.locale.get_display_name()},
                url=reverse("wagtailadmin_pages:edit", args=(page.pk,)),
                icon_name="edit",
            )
        ]
        translated_locales = Page.objects.filter(
            translation_key=page.translation_key, alias_of__isnull=True
        ).values("locale_id")
        if Locale.objects.exclude(pk__in=translated_locales).exists():
            buttons.append(
                HeaderButton(
                    label=_("Translate into more locales"),
                    url=reverse(
                        "wagtail_localize:submit_page_translation", args=(page.pk,)
                    ),
                    icon_name="wagtail-localize-language",
                )
            )
        # wagtail-localize's own condition for syncing, plus an unsynced change.
        if (
            page.latest_revision_created_at
            and page.latest_revision_created_at > self.source.last_updated_at
            and self.source.translations.filter(enabled=True).exists()
        ):
            buttons.append(
                HeaderButton(
                    label=_("Sync translated pages"),
                    url=reverse(
                        "wagtail_localize:update_translations", args=(self.source.pk,)
                    ),
                    icon_name="resubmit",
                )
            )
        return buttons

    def get_queryset(self):
        return (
            Translation.objects.filter(source=self.source)
            .exclude(target_locale_id=self.object.locale_id)
            .select_related("source", "target_locale")
            .order_by("target_locale__language_code")
        )

    def get_translated_via(self, translation):
        segments = StringSegment.objects.filter(source=self.source)
        rows = (
            StringTranslation.objects.filter(
                locale_id=translation.target_locale_id,
                translation_of_id__in=segments.values("string_id"),
                context_id__in=segments.values("context_id"),
                has_error=False,
            )
            .values("tool_name")
            .annotate(
                count=Count("pk"),
                manual=Count("pk", filter=Q(last_translated_by__isnull=False)),
            )
        )
        counts = {}
        for row in rows:
            if row["tool_name"]:
                counts[row["tool_name"]] = (
                    counts.get(row["tool_name"], 0) + row["count"]
                )
                continue
            for label, count in (
                (_("Manual"), row["manual"]),
                (_("Other tool"), row["count"] - row["manual"]),
            ):
                if count:
                    counts[label] = counts.get(label, 0) + count
        if not counts:
            return _("Not translated yet")
        return format_html(
            "<ul>{}</ul>",
            format_html_join("", "<li>{} ({})</li>", sorted(counts.items())),
        )

    def get_table(self, object_list, **kwargs):
        pages = {
            page.locale_id: page
            for page in Page.objects.filter(translation_key=self.object.translation_key)
        }
        # shortcut: a few queries per row, fine for a page's handful of locales.
        for translation in object_list:
            page = pages.get(translation.target_locale_id)
            total, translated = translation.get_progress()
            translation.target_page = page
            translation.is_alias = bool(page and page.alias_of_id)
            translation.translated_html = progress_html(translated, total)
            if page is None:
                translation.published_html = mark_safe("<span>-</span>")
            else:
                published = _count_published(
                    self.source, translation.target_locale, page
                )
                translation.published_html = progress_html(
                    min(published, translated), total
                )
            translation.translated_via = self.get_translated_via(translation)
        return super().get_table(object_list, **kwargs)

    @staticmethod
    def get_locale_html(translation):
        name = translation.target_locale.get_display_name()
        if translation.is_alias:
            name = _("%(locale)s (alias)") % {"locale": name}
        page = translation.target_page
        if page is None:
            return format_html(
                '<span id="translation_{}_title">{}</span>', translation.pk, name
            )
        return format_html(
            '<a id="translation_{}_title" href="{}">{}</a>',
            translation.pk,
            reverse("wagtailadmin_pages:edit", args=(page.pk,)),
            name,
        )

    @staticmethod
    def get_status(translation):
        page = translation.target_page
        if page is None:
            return _("Not created yet")
        return render_to_string(
            "wagtail_localize_dashboard/includes/page_status.html",
            {"page": page, "show_last_published": True},
        )

    @cached_property
    def columns(self):
        return [
            tables.BulkActionsCheckboxColumn("bulk_actions", obj_type="translation"),
            tables.Column("locale", label=_("Locale"), accessor=self.get_locale_html),
            tables.Column(
                "translated", label=_("Translated"), accessor="translated_html"
            ),
            tables.Column("published", label=_("Published"), accessor="published_html"),
            tables.Column("status", label=_("Page status"), accessor=self.get_status),
            tables.Column(
                "translated_via", label=_("Translated via"), accessor="translated_via"
            ),
        ]


class TranslationBulkAction(BulkAction):
    """A bulk action on wagtail-localize Translations, with ineligible items set aside."""

    models = (Translation,)
    template_name = "wagtail_localize_dashboard/confirm_bulk_action.html"

    @classmethod
    def get_queryset(cls, model, object_ids):
        return list(
            model.objects.filter(pk__in=object_ids)
            .select_related("source", "target_locale")
            .order_by("target_locale__language_code")
        )

    def is_eligible(self, translation):
        return True

    def has_perm(self, translation):
        return True

    def check_perm(self, translation):
        # Ineligible items are set aside separately, whatever the permissions.
        return not self.is_eligible(translation) or self.has_perm(translation)

    def get_actionable_objects(self):
        objects, context = super().get_actionable_objects()
        context["items_ineligible"] = [o for o in objects if not self.is_eligible(o)]
        return [o for o in objects if self.is_eligible(o)], context

    def get_execution_context(self):
        return {"user": self.request.user}

    def get_success_text(self, count):
        raise NotImplementedError

    def get_success_message(self, num_parent_objects, num_child_objects):
        # Django's messages, not Wagtail's, which wrap the text in markup.
        messages.success(self.request, self.get_success_text(num_parent_objects))


class PublishTranslationBulkAction(TranslationBulkAction):
    display_name = gettext_lazy("Publish")
    action_type = "publish"
    aria_label = gettext_lazy("Publish selected translations")
    action_priority = 10
    confirm_text = gettext_lazy("Are you sure you want to publish these translations?")
    action_button_text = gettext_lazy("Yes, publish")
    no_action_button_text = gettext_lazy("No, don't publish")
    no_access_text = gettext_lazy("You don't have permission to publish these:")
    ineligible_text = gettext_lazy("These translations are not syncing:")

    def is_eligible(self, translation):
        return translation.enabled

    def has_perm(self, translation):
        # A missing target page is created under the source page.
        page = get_target_page(translation) or translation.source.get_source_instance()
        return page.permissions_for_user(self.request.user).can_publish()

    @classmethod
    def execute_action(cls, objects, user=None, **kwargs):
        for translation in objects:
            translation.save_target(user=user, publish=True)
        return len(objects), 0

    def get_success_text(self, count):
        return ngettext(
            "%(count)d translation has been published",
            "%(count)d translations have been published",
            count,
        ) % {"count": count}


class UnpublishTranslationBulkAction(TranslationBulkAction):
    display_name = gettext_lazy("Unpublish")
    action_type = "unpublish"
    aria_label = gettext_lazy("Unpublish selected translations")
    action_priority = 20
    confirm_text = gettext_lazy(
        "Are you sure you want to unpublish these translations?"
    )
    action_button_text = gettext_lazy("Yes, unpublish")
    no_action_button_text = gettext_lazy("No, don't unpublish")
    no_access_text = gettext_lazy("You don't have permission to unpublish these:")
    ineligible_text = gettext_lazy("These translations have no live page:")

    def is_eligible(self, translation):
        page = get_target_page(translation)
        return page is not None and page.live

    def has_perm(self, translation):
        page = get_target_page(translation)
        return page.permissions_for_user(self.request.user).can_unpublish()

    @classmethod
    def execute_action(cls, objects, user=None, **kwargs):
        for translation in objects:
            get_target_page(translation).unpublish(user=user)
        return len(objects), 0

    def get_success_text(self, count):
        return ngettext(
            "%(count)d translation has been unpublished",
            "%(count)d translations have been unpublished",
            count,
        ) % {"count": count}
