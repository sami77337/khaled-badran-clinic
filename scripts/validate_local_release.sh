#!/usr/bin/env bash
set -u

find_repo_root() {
  local current
  current="$(pwd)"
  while true; do
    if [[ -f "$current/manage.py" && -d "$current/.git" ]]; then
      printf '%s\n' "$current"
      return 0
    fi
    local parent
    parent="$(dirname "$current")"
    if [[ -z "$parent" || "$parent" == "$current" ]]; then
      printf 'Could not locate repository root containing manage.py and .git.\n' >&2
      return 1
    fi
    current="$parent"
  done
}

redact_output() {
  sed -E \
    -e 's/(DJANGO_SECRET_KEY|SECRET_KEY|DATABASE_URL|CACHE_URL|PASSWORD|TOKEN|DSN)[[:space:]]*=[^[:space:]]+/\1=<redacted>/Ig' \
    -e 's#(postgres|postgresql|redis|rediss)://[^[:space:]]+#<redacted-url>#Ig'
}

run_safe() {
  printf '\n$'
  printf ' %q' "$@"
  printf '\n'

  local output status
  output="$("$@" 2>&1)"
  status=$?
  printf '%s\n' "$output" | redact_output
  if [[ $status -ne 0 ]]; then
    printf 'Command failed with exit code %s:' "$status" >&2
    printf ' %q' "$@" >&2
    printf '\n' >&2
    return "$status"
  fi
}

main() {
  local repo_root
  repo_root="$(find_repo_root)" || return 1
  cd "$repo_root" || return 1

  printf 'Local release validation for Dr. Khaled Badran Clinic\n'
  printf 'Repository root: %s\n' "$repo_root"

  run_safe git branch --show-current || return 1
  run_safe git rev-parse HEAD || return 1
  run_safe python manage.py makemigrations --check --dry-run || return 1
  run_safe python manage.py migrate || return 1
  run_safe python manage.py check || return 1
  run_safe python manage.py deployment_smoke || return 1
  run_safe python manage.py project_status_report || return 1
  run_safe python manage.py test || return 1

  printf '\nLocal release validation completed.\n'
}

main "$@"
