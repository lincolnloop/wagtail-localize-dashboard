# Large-Scale Testing Guide

This guide explains how to test the wagtail-localize-dashboard with a large number of pages and locales to evaluate performance.

## Overview

The example project has been configured to support **40 locales** and includes scripts to generate **1000 pages** with full translations, creating up to **40,000 total page instances** for comprehensive performance testing.

## Prerequisites

1. Set up the example project:
   ```bash
   cd example
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Create the database and run migrations:
   ```bash
   python manage.py migrate
   ```

## Step-by-Step Setup

### Step 1: Set Up Demo Site

First, create the basic demo structure with a superuser and home page:

```bash
python manage.py setup_demo
```

This creates:
- A superuser (username: `admin`, password: `admin`)
- A home page in English
- A few sample articles and products

**Login credentials:** `admin` / `admin`

### Step 2: Create All 40 Locales

Create all 40 locales in the database:

```bash
python manage.py setup_locales
```

This creates locale records for:
- English, German, Spanish, French, Italian, Portuguese, Dutch, Polish, Russian
- Japanese, Chinese (Simplified & Traditional), Korean, Arabic, Turkish
- Swedish, Norwegian, Danish, Finnish, Czech, Hungarian, Romanian, Ukrainian
- Greek, Hebrew, Hindi, Thai, Vietnamese, Indonesian, Malay, Tagalog
- Bengali, Persian, Urdu, Swahili, Tamil, Telugu, Marathi, Punjabi, Gujarati

**Total:** 40 locales

### Step 3: Generate 1000 Pages with Translations

Generate 1000 pages in English and translate them into all 39 other locales:

```bash
python manage.py generate_pages
```

**Options:**
- `--pages N`: Number of source pages to create (default: 1000)
- `--skip-translations`: Only create source pages without translations
- `--batch-size N`: Batch size for progress reporting (default: 50)

**Examples:**
```bash
# Generate 1000 pages with all translations (default)
python manage.py generate_pages

# Generate 500 pages with translations
python manage.py generate_pages --pages 500

# Generate 100 pages without translations (for testing source page creation only)
python manage.py generate_pages --pages 100 --skip-translations

# Generate 2000 pages with custom batch size
python manage.py generate_pages --pages 2000 --batch-size 100
```

**What this creates:**
- 1000 source pages in English (mix of ArticlePage and ProductPage)
- 39,000 translated pages (1000 pages × 39 target locales)
- **Total: 40,000 page instances**

**Estimated time:**
- Creating 1000 source pages: ~2-5 minutes
- Creating 39,000 translations: ~30-60 minutes (depending on hardware)
- Total: ~35-65 minutes

### Step 4: Build Translation Progress Cache

After creating all pages and translations, build the translation progress cache:

```bash
python manage.py rebuild_translation_progress
```

This command:
- Calculates translation completion percentages for all pages
- Stores them in the `TranslationProgress` table for fast dashboard loading
- Shows statistics on processed pages

**Estimated time:** ~5-10 minutes for 1000 pages with 40 locales

## Viewing the Dashboard

1. Start the development server:
   ```bash
   python manage.py runserver
   ```

2. Visit the admin:
   ```
   http://localhost:8000/admin/
   ```
   Login: `admin` / `admin`

3. View the translation dashboard:
   ```
   http://localhost:8000/admin/translations/
   ```

## Performance Testing Scenarios

### Scenario 1: Basic Dashboard Load Time
- Navigate to `/admin/translations/`
- Measure time to first render
- Expected: <2 seconds with caching enabled

### Scenario 2: Filtering Performance
- Filter by original language (e.g., English)
- Filter by exists in language (e.g., German)
- Search by title
- Expected: <1 second for each filter

### Scenario 3: Pagination
- Navigate through pages (50 items per page)
- Test with different page sizes
- Expected: Consistent load times across pages

### Scenario 4: Translation Progress Accuracy
- Spot-check translation percentages
- Verify color coding (Green: 100%, Yellow: 80-99%, Red: <80%)
- Test with partially translated pages

### Scenario 5: Real-Time Updates
- Edit a page translation
- Check if dashboard updates automatically (via signals)
- Verify percentage recalculation

## Database Statistics

After full setup, you should have:

| Table | Records |
|-------|---------|
| `wagtailcore_page` | ~40,000 |
| `wagtailcore_locale` | 40 |
| `wagtail_localize_translationsource` | ~1,000 |
| `wagtail_localize_translation` | ~39,000 |
| `wagtail_localize_dashboard_translationprogress` | ~39,000 |

## Cleaning Up

To reset and start over:

```bash
# Delete the database
rm db.sqlite3

# Run migrations
python manage.py migrate

# Start over from Step 1
python manage.py setup_demo
```

Or to keep the database but remove generated content:

```bash
# Delete all pages except root and home
python manage.py shell
>>> from wagtail.models import Page
>>> Page.objects.filter(depth__gt=2).exclude(slug='home').delete()
```

## Benchmarking Tips

1. **Enable query logging** to analyze database performance:
   ```python
   # In settings.py
   LOGGING = {
       'version': 1,
       'handlers': {
           'console': {
               'class': 'logging.StreamHandler',
           },
       },
       'loggers': {
           'django.db.backends': {
               'level': 'DEBUG',
               'handlers': ['console'],
           },
       },
   }
   ```

2. **Use Django Debug Toolbar** for detailed profiling:
   ```bash
   pip install django-debug-toolbar
   ```

3. **Monitor memory usage** during generation:
   ```bash
   # On Linux
   watch -n 1 'ps aux | grep python'
   ```

4. **Profile the dashboard view**:
   ```bash
   python -m cProfile -s cumulative manage.py shell
   >>> from django.test import RequestFactory
   >>> from wagtail_localize_dashboard.views import ProgressDashboardView
   # ... profile the view
   ```

## Expected Performance Metrics

Based on the implementation plan, with 1000 pages and 40 locales:

| Metric | Without Cache | With Cache |
|--------|--------------|------------|
| Dashboard Load Time | 30+ seconds | <2 seconds |
| Filter Query Time | 5+ seconds | <1 second |
| Memory Usage (Dashboard) | ~500 MB | ~50 MB |
| Translation Progress Update | N/A | <100ms per page |

## Troubleshooting

### Problem: Out of Memory during generation
**Solution:** Reduce batch size or number of pages:
```bash
python manage.py generate_pages --pages 500
```

### Problem: Translation creation is very slow
**Solution:** Disable auto-update signals temporarily:
```python
# In settings.py
WAGTAIL_LOCALIZE_DASHBOARD_AUTO_UPDATE = False
```
Then rebuild the cache manually after generation:
```bash
python manage.py rebuild_translation_progress
```

### Problem: Dashboard is slow even with cache
**Solution:** Check database indexes:
```bash
python manage.py sqlmigrate wagtail_localize_dashboard 0001
```
Ensure indexes exist on `TranslationProgress` table.

### Problem: Missing locales
**Solution:** Run setup_locales again:
```bash
python manage.py setup_locales
```

## Advanced: Custom Testing Scripts

You can create your own test scenarios by using the Django shell:

```bash
python manage.py shell
```

```python
from wagtail.models import Locale, Page
from wagtail_localize_dashboard.models import TranslationProgress
from wagtail_localize_dashboard.utils import rebuild_all_progress
from django.utils import timezone
import time

# Test cache rebuild performance
start = timezone.now()
stats = rebuild_all_progress()
elapsed = (timezone.now() - start).total_seconds()
print(f"Rebuilt {stats['pages']} pages in {elapsed:.2f}s")

# Test query performance
start = time.time()
progress_records = TranslationProgress.objects.all()[:100]
elapsed = time.time() - start
print(f"Queried 100 records in {elapsed*1000:.2f}ms")

# Check translation coverage
total_pages = Page.objects.filter(depth__gt=2).count()
total_locales = Locale.objects.count()
expected_translations = (total_pages // total_locales) * (total_locales - 1)
actual_translations = TranslationProgress.objects.count()
coverage = (actual_translations / expected_translations) * 100
print(f"Translation coverage: {coverage:.1f}%")
```

## Conclusion

This large-scale testing setup allows you to evaluate the wagtail-localize-dashboard performance under realistic conditions. The caching mechanism should demonstrate significant performance improvements compared to calculating translation progress on the fly.

For questions or issues, please refer to the main README or open an issue on the GitHub repository.
