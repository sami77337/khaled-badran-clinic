#!/usr/bin/env sh
# Run on the actual service instance: Render build/pre-deploy cannot see disks.
set -eu

python manage.py check_media_storage --write-probe
exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-10000}" --access-logfile - --error-logfile - "$@"
