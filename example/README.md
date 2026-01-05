# wagtail-localize-dashboard Example Project

This is an example Django/Wagtail project demonstrating the wagtail-localize-dashboard package.

## Features Demonstrated

- Multi-language Wagtail site with support for 40 locales
- Translatable page models with various field types
- Translation dashboard showing progress for all pages
- Automatic cache updates when translations are saved
- Filtering by language and search functionality
- **Large-scale testing**: Generate 1000 pages with 40 locales (40,000 total pages)

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run Setup Script

```bash
./setup.sh
```

This will:
- Run database migrations
- Create a superuser (admin/admin)
- Set up locales (English, German, Spanish)
- Create sample pages
- Build translation progress cache

### 3. Start the Development Server

```bash
python manage.py runserver
```

### 4. Access the Site

- **Admin Interface**: http://localhost:8000/admin/
- **Translation Dashboard**: http://localhost:8000/admin/translations/
- **Login**: admin / admin

## What to Try

1. **View the Dashboard**: Navigate to "Translations" in the Wagtail admin menu
2. **Create a Translation**:
   - Go to a page in the admin
   - Use Wagtail Localize to create a translation
   - Watch the dashboard update automatically
3. **Filter Results**: Use the search and filter options in the dashboard
4. **View Progress**: See color-coded translation status (green=100%, yellow=80-99%, red=<80%)

## Project Structure

```
example/
├── manage.py              # Django management script
├── setup.sh               # Setup script
├── requirements.txt       # Python dependencies
├── demo/                  # Django project
│   ├── settings.py        # Django settings
│   ├── urls.py            # URL configuration
│   └── wsgi.py            # WSGI entry point
└── home/                  # Demo app
    ├── models.py          # Translatable page models
    ├── templates/         # Page templates
    └── management/
        └── commands/
            └── setup_demo.py  # Demo setup command
```

## Configuration Notes

The example includes several configuration options in `demo/settings.py`:

```python
# Enable the dashboard
WAGTAIL_LOCALIZE_DASHBOARD_ENABLED = True

# Auto-update cache when translations change
WAGTAIL_LOCALIZE_DASHBOARD_AUTO_UPDATE = True

# Track Pages (enabled)
WAGTAIL_LOCALIZE_DASHBOARD_TRACK_PAGES = True

# Show in admin menu
WAGTAIL_LOCALIZE_DASHBOARD_SHOW_IN_MENU = True
```

## Large-Scale Performance Testing

The example project now supports testing with **1000 pages** across **40 locales** (40,000 total page instances).

### Quick Start for Large-Scale Testing

1. **Set up the base demo**:
   ```bash
   python manage.py setup_demo
   ```

2. **Create all 40 locales**:
   ```bash
   python manage.py setup_locales
   ```

3. **Generate 1000 pages with translations**:
   ```bash
   python manage.py generate_pages
   ```
   This creates 1000 source pages in English and translates them into 39 other locales (39,000 translations).

4. **Build the translation progress cache**:
   ```bash
   python manage.py rebuild_translation_progress
   ```

5. **View the dashboard** at http://localhost:8000/admin/translations/

### Available Commands

- `setup_demo` - Create basic demo site with superuser and sample pages
- `setup_locales` - Create all 40 configured locales in the database
- `generate_pages` - Generate many pages for performance testing
  - `--pages N` - Number of pages to create (default: 1000)
  - `--skip-translations` - Only create source pages
  - `--batch-size N` - Batch size for progress reporting
- `rebuild_translation_progress` - Rebuild the translation progress cache

### Supported Locales (40 total)

English, German, Spanish, French, Italian, Portuguese, Dutch, Polish, Russian, Japanese, Chinese (Simplified & Traditional), Korean, Arabic, Turkish, Swedish, Norwegian, Danish, Finnish, Czech, Hungarian, Romanian, Ukrainian, Greek, Hebrew, Hindi, Thai, Vietnamese, Indonesian, Malay, Tagalog, Bengali, Persian, Urdu, Swahili, Tamil, Telugu, Marathi, Punjabi, Gujarati

### Detailed Testing Guide

See [TESTING_LARGE_SCALE.md](TESTING_LARGE_SCALE.md) for comprehensive information on:
- Performance testing scenarios
- Benchmarking tips
- Expected metrics
- Troubleshooting
- Advanced testing scripts

## Development

To reset the database and start fresh:

```bash
rm db.sqlite3
./setup.sh
```

Or for large-scale testing:

```bash
rm db.sqlite3
python manage.py migrate
python manage.py setup_demo
python manage.py setup_locales
python manage.py generate_pages
python manage.py rebuild_translation_progress
```

## License

This example project is released under the MIT License, same as wagtail-localize-dashboard.
