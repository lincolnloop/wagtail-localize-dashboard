"""
Example page models demonstrating translatable content.
"""

from django.db import models

from wagtail import blocks
from wagtail.admin.panels import FieldPanel
from wagtail.fields import RichTextField, StreamField
from wagtail.models import Page


class HomePage(Page):
    """
    Home page with translatable content.
    """

    tagline = models.CharField(
        max_length=255,
        blank=True,
        help_text="A short tagline for the homepage",
    )

    intro = RichTextField(
        blank=True,
        help_text="Introduction text for the homepage",
    )

    body = StreamField(
        [
            ("heading", blocks.CharBlock(form_classname="title")),
            ("paragraph", blocks.RichTextBlock()),
            (
                "image",
                blocks.StructBlock(
                    [
                        ("image", blocks.CharBlock(help_text="Image URL or path")),
                        ("caption", blocks.CharBlock(required=False)),
                    ]
                ),
            ),
        ],
        blank=True,
        use_json_field=True,
    )

    content_panels = Page.content_panels + [
        FieldPanel("tagline"),
        FieldPanel("intro"),
        FieldPanel("body"),
    ]

    class Meta:
        verbose_name = "Home Page"


class ArticlePage(Page):
    """
    Article page with translatable content.
    """

    date = models.DateField("Post date")
    intro = models.TextField(
        blank=True,
        help_text="Brief introduction to the article",
    )
    body = RichTextField(blank=True)

    author = models.CharField(
        max_length=255,
        blank=True,
        help_text="Article author name",
    )

    content_panels = Page.content_panels + [
        FieldPanel("date"),
        FieldPanel("intro"),
        FieldPanel("body"),
        FieldPanel("author"),
    ]

    class Meta:
        verbose_name = "Article Page"
        verbose_name_plural = "Article Pages"


class ProductPage(Page):
    """
    Product page with translatable content.
    """

    description = RichTextField(
        blank=True,
        help_text="Product description",
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Product price (not translated)",
    )

    sku = models.CharField(
        max_length=50,
        blank=True,
        help_text="Product SKU (not translated)",
    )

    features = StreamField(
        [
            (
                "feature",
                blocks.StructBlock(
                    [
                        ("title", blocks.CharBlock()),
                        ("description", blocks.TextBlock()),
                    ]
                ),
            ),
        ],
        blank=True,
        use_json_field=True,
    )

    content_panels = Page.content_panels + [
        FieldPanel("description"),
        FieldPanel("price"),
        FieldPanel("sku"),
        FieldPanel("features"),
    ]

    class Meta:
        verbose_name = "Product Page"
        verbose_name_plural = "Product Pages"
