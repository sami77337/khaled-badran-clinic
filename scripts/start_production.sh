#!/usr/bin/env sh
# Run on the actual service instance: Render build/pre-deploy cannot see disks.
set -eu

# Keep management commands and WSGI on the same production settings.
export DJANGO_SETTINGS_MODULE=config.settings.prod

# Apply committed schema migrations before serving traffic. This is idempotent and
# prevents code/schema drift when a deploy introduces a required migration.
python manage.py migrate --noinput
python manage.py check_media_storage --write-probe
exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-10000}" --access-logfile - --error-logfile - "$@"
