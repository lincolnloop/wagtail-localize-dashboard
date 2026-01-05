#!/bin/bash

# Setup script for wagtail-localize-dashboard example project

set -e

echo "Setting up wagtail-localize-dashboard example..."

# Run migrations
echo "Running migrations..."
python manage.py migrate

# Set up demo data
echo "Setting up demo data..."
python manage.py setup_demo

# Build translation progress cache
echo "Building translation progress cache..."
python manage.py rebuild_translation_progress

echo ""
echo "Setup complete!"
echo ""
echo "You can now start the development server with:"
echo "  python manage.py runserver"
echo ""
echo "Then visit:"
echo "  Admin: http://localhost:8000/admin/"
echo "  Dashboard: http://localhost:8000/admin/translations/"
echo "  Login: admin / admin"
echo ""
