# wagtail-localize-dashboard

A translation dashboard for Wagtail sites using [wagtail-localize](https://github.com/wagtail/wagtail-localize).

<img width="1914" height="470" alt="translation-dashboard" src="https://github.com/user-attachments/assets/c536fc1e-9a9e-4137-aa9b-9faa2baf74c1" />

## Features

- **Translation Dashboard**: Visual overview of translation progress for all pages
- **Auto-Updates**: Signals automatically update percentages when translations change
- **Performance**: Translation percentages are stored in the database, for fast loading
- **Filtering**: Search by title, filter by language, translation key
- **Color-Coded Status**: Green (100%), Yellow (80-99%), Red (<80%)
- **Admin Integration**: Adds menu item to Wagtail admin
- **Configurable**: Enable/disable features via Django settings

## Installation

```bash
pip install wagtail-localize-dashboard
```

## Quick Start

### 1. Add to INSTALLED_APPS

```python
# settings.py

INSTALLED_APPS = [
    # ... other apps
    "wagtail_localize",
    "wagtail_localize_dashboard",  # Add after wagtail-localize
    # ... other apps
]
```

### 2. Include URLs

```python
# urls.py

from django.urls import path, include

urlpatterns = [
    # ... other patterns
    path("translations/", include("wagtail_localize_dashboard.urls")),
    # ... other patterns
]
```

### 3. Run Migrations

```bash
python manage.py migrate wagtail_localize_dashboard
```

### 4. Calculate Percentages

```bash
python manage.py rebuild_translation_progress
```

### 5. Access Dashboard

Navigate to `/translations/` in your Wagtail admin, or click "Translations" in the admin menu.

## Configuration

Customize behavior in your Django settings:

```python
# settings.py

# Enable/disable the entire feature (default: True)
WAGTAIL_LOCALIZE_DASHBOARD_ENABLED = True

# Enable automatic TranslationProgress updates via signals (default: True)
WAGTAIL_LOCALIZE_DASHBOARD_AUTO_UPDATE = True

# Track translation progress for Pages (default: True)
WAGTAIL_LOCALIZE_DASHBOARD_TRACK_PAGES = True

# Show dashboard in Wagtail admin menu (default: True)
WAGTAIL_LOCALIZE_DASHBOARD_SHOW_IN_MENU = True

# Menu item configuration
WAGTAIL_LOCALIZE_DASHBOARD_MENU_LABEL = "Translations"
WAGTAIL_LOCALIZE_DASHBOARD_MENU_ICON = "wagtail-localize-language"
WAGTAIL_LOCALIZE_DASHBOARD_MENU_ORDER = 800

# Items per page in dashboard (default: 50)
WAGTAIL_LOCALIZE_DASHBOARD_ITEMS_PER_PAGE = 50
```

## Usage

### Dashboard

The dashboard shows:
- All original pages (not translations)
- Translation progress for each locale (0-100%)
- Color-coded status badges
- Quick links to edit pages

### Management Commands

```bash
# Recalculate translation percentages for all pages
python manage.py rebuild_translation_progress

# Clean orphaned records and rebuild
python manage.py rebuild_translation_progress --clean-orphans
```

### Programmatic API

```python
from wagtail_localize_dashboard.utils import (
    get_translation_percentages,
    create_translation_progress,
    rebuild_all_progress,
)

# Get translation percentage for a specific locale
from wagtail.models import Locale
page = Page.objects.get(id=123)
locale_de = Locale.objects.get(language_code="de")
percent = get_translation_percentages(page, locale_de)

# Update progress for a page
create_translation_progress(page)

# Rebuild all progress
stats = rebuild_all_progress()
print(f"Processed {stats['pages']} pages")
```

## How It Works

1. **Database Table**: The `TranslationProgress` model stores pre-calculated percentages
2. **Signals**: Listen for translation changes and update `TranslationProgress` table automatically
3. **Dashboard**: Displays `TranslationProgress` data for each page
4. **Management Command**: Rebuilds `TranslationProgress` objects when needed

## Requirements

- Python 3.10+
- Django 4.2+
- Wagtail 5.2+
- wagtail-localize 1.8+

## Contributing

Contributions are welcome!

## Development

### Setting Up for Development

1. Clone the repository:
```bash
git clone https://github.com/lincolnloop/wagtail-localize-dashboard.git
cd wagtail-localize-dashboard
```

2. Install the package with development dependencies:
```bash
pip install -e ".[dev]"
```

This installs the package in editable mode along with testing tools.

### Running Tests

Run the test suite with pytest:
```bash
pytest
```

Run tests with coverage:
```bash
pytest --cov=wagtail_localize_dashboard
```

Run specific test files:
```bash
pytest tests/test_utils.py
pytest tests/test_views.py
```

Run accessibility tests (requires `pip install -e ".[test,accessibility]"`):
```bash
pytest -m accessibility
```

### Code Quality

Check code with ruff:
```bash
ruff check .
```

Format with ruff:
```bash
ruff format .
```

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Credits

Created by [Lincoln Loop](https://lincolnloop.com/) for the Wagtail community.

Inspired by the translation dashboard in the Springfield CMS.
