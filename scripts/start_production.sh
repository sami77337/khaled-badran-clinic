#!/usr/bin/env sh
# Run on the actual service instance: Render build/pre-deploy cannot see disks.
set -eu

# Keep the management command and WSGI process on the same production settings.
export DJANGO_SETTINGS_MODULE=config.settings.prod

python manage.py check_media_storage --write-probe
exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-10000}" --access-logfile - --error-logfile - "$@"
